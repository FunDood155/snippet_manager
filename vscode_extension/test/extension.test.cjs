const assert = require('node:assert/strict');
const { test } = require('node:test');
const Module = require('node:module');
const { credentialKey, extensionId } = require('../out/auth.js');

const origin = 'https://snippets.example.test';
const config = { provider: 'https://auth.example.test', clientId: 'client-id', redirectUri: origin + '/oauth/vscode/callback' };

test('browser sign-in gates existing commands, supports cancel, and makes authorized requests', async t => {
    const commands = new Map();
    const secret = new Map();
    const messages = [];
    const requested = [];
    const picked = [];
    const progressMessages = [];
    let inserted;
    let handleUri;
    let cancelProgress;
    let openBrowser;
    let changeConfiguration;
    const disposable = () => ({ dispose() {} });
    let hidePicker;
    let readyPicker = () => undefined;
    let waitForList;
    let revokeList = false;
    let offline = false;
    let changedSecret;
    function createQuickPick() {
        let accept;
        let hide;
        let items = [];
        const picker = {
            busy: false,
            selectedItems: [],
            get items() { return items; },
            set items(value) {
                items = value;
                picked.push(value);
                picker.selectedItems = value.slice(0, 1);
                queueMicrotask(() => accept?.());
            },
            onDidHide(fn) { hide = fn; return { dispose() { hide = undefined; } }; },
            onDidAccept(fn) { accept = fn; return { dispose() { accept = undefined; } }; },
            show() { hidePicker = () => picker.hide(); readyPicker(picker); },
            hide() { hide?.(); },
            dispose() { picker.hide(); },
        };
        return picker;
    }
    const vscode = {
        commands: {
            registerCommand(name, callback) { commands.set(name, callback); return disposable(); },
            executeCommand: name => commands.get(name)(),
        },
        env: {
            uriScheme: 'vscode',
            openExternal: async uri => (await openBrowser(uri)) ?? true,
        },
        Uri: { parse: value => new URL(value) },
        StatusBarAlignment: { Right: 2 },
        ProgressLocation: { Notification: 3 },
        workspace: {
            getConfiguration: () => ({ get: () => origin }),
            onDidChangeConfiguration: listener => { changeConfiguration = listener; return disposable(); },
        },
        window: {
            createStatusBarItem: () => ({ show() {}, dispose() {} }),
            registerUriHandler: handler => { handleUri = handler.handleUri; return disposable(); },
            showInformationMessage: async message => { messages.push(message); },
            showWarningMessage: async message => { messages.push(message); },
            showErrorMessage: async message => { messages.push(message); },
            showInputBox: async () => 'cat + &',
            createQuickPick,
            activeTextEditor: {
                selection: { active: { line: 0, character: 0 } },
                edit: async callback => { callback({ insert: (_position, code) => { inserted = code; } }); return true; },
            },
            withProgress: (_options, callback) => {
                const listeners = new Set();
                const token = {
                    isCancellationRequested: false,
                    onCancellationRequested(fn) {
                        listeners.add(fn);
                        return { dispose() { listeners.delete(fn); } };
                    },
                };
                cancelProgress = () => {
                    token.isCancellationRequested = true;
                    for (const listener of listeners) { listener(); }
                };
                return callback({ report: progress => progressMessages.push(progress.message) }, token);
            },
        },
    };
    const context = {
        subscriptions: [],
        secrets: {
            get: async key => secret.get(key),
            store: async (key, value) => { secret.set(key, value); },
            delete: async key => { secret.delete(key); },
            onDidChange(listener) { changedSecret = listener; return disposable(); },
        },
    };
    t.mock.method(global, 'fetch', async (url, init) => {
        const target = new URL(url);
        requested.push(target);
        if (target.pathname === '/oauth/vscode/config') { return Response.json(config); }
        if (target.pathname.endsWith('/token')) {
            if (init.body.get('grant_type') === 'refresh_token') {
                if (revokeList) return new Response(null, { status: 401 });
                return Response.json({ access_token: 'access', refresh_token: 'refresh', expires_in: 3600 });
            }
            assert.equal(init.body.get('code'), 'browser-fixture');
            assert.ok(init.body.get('code_verifier'));
            return Response.json({ access_token: 'access', refresh_token: 'refresh', expires_in: 3600 });
        }
        assert.equal(init.headers.Authorization, 'Bearer access');
        if (target.pathname.endsWith('/logout')) { return new Response(null, { status: 204 }); }
        if (waitForList) await waitForList(init.signal);
        if (offline) throw new Error('Offline');
        if (revokeList) return new Response(null, { status: 401 });
        return Response.json([{ name: 'Snippet fixture', cat: 'Test', code: 'print(5)' }]);
    });
    const load = Module._load;
    const loader = t.mock.method(Module, '_load', (name, ...args) => name === 'vscode' ? vscode : load(name, ...args));
    const { activate } = require('../out/extension.js');
    loader.mock.restore();
    activate(context);
    const run = name => commands.get('code-snippet-manager.' + name)();

    await run('showSnippets');
    assert.equal(requested.length, 0);
    assert.match(messages[0], /Sign in/);

    openBrowser = async () => { cancelProgress(); };
    await run('signIn');
    assert.equal(secret.size, 0);

    openBrowser = async () => false;
    await run('signIn');
    assert.match(messages.at(-1), /Could not open/);
    openBrowser = async () => { throw new Error('Browser unavailable'); };
    await run('signIn');
    assert.match(messages.at(-1), /Could not open/);

    openBrowser = async url => {
        const state = url.searchParams.get('state');
        handleUri({ scheme: 'vscode', authority: extensionId, path: '/auth', fragment: '',
            query: 'state=' + state + '&error=access_denied' });
    };
    await run('signIn');
    assert.match(messages.at(-1), /cancelled in the browser/);

    async function launchWhileBrowserIsPending() {
        let launched;
        const ready = new Promise(resolve => { launched = resolve; });
        openBrowser = uri => { launched(uri); return new Promise(() => {}); };
        const running = run('signIn');
        return { running, uri: await ready };
    }

    let pending = await launchWhileBrowserIsPending();
    await run('signOut');
    await pending.running;
    pending = await launchWhileBrowserIsPending();
    changeConfiguration({ affectsConfiguration: name => name === 'snippetManager.serverUrl' });
    await pending.running;
    t.mock.timers.enable({ apis: ['setTimeout'] });
    pending = await launchWhileBrowserIsPending();
    t.mock.timers.tick(5 * 60_000);
    await pending.running;
    t.mock.timers.reset();
    assert.match(messages.at(-1), /Sign-in expired/);
    handleUri({ scheme: 'vscode', authority: extensionId, path: '/auth', fragment: '',
        query: 'state=' + pending.uri.searchParams.get('state') + '&code=late' });
    assert.equal(secret.size, 0);
    assert.equal(requested.filter(request => request.pathname.endsWith('/token')).length, 0);

    openBrowser = async url => {
        assert.equal(url.origin, config.provider);
        const state = url.searchParams.get('state');
        const callback = { scheme: 'vscode', authority: extensionId, path: '/auth', fragment: '' };
        handleUri({ ...callback, query: 'state=bad&code=wrong' });
        handleUri({ ...callback, query: 'state=' + state + '&code=browser-fixture' });
        handleUri({ ...callback, query: 'state=' + state + '&code=browser-fixture' });
    };
    await run('signIn');
    assert.ok(secret.has(credentialKey));
    assert.ok(progressMessages.some(message => /return to VS Code/.test(message)));
    assert.ok(progressMessages.some(message => /Finishing sign-in/.test(message)));
    assert.equal(requested.filter(request => request.pathname.endsWith('/token')).length, 1);

    await run('showSnippets');
    await run('searchSnippets');
    await run('insertSnippet');
    assert.equal(picked.length, 3);
    assert.equal(picked[0][0].label, 'Snippet fixture');
    assert.equal(requested.find(request => request.search).searchParams.get('search'), 'cat + &');
    assert.equal(inserted, 'print(5)');

    let release;
    waitForList = () => new Promise(resolve => { release = resolve; });
    let busyShown = 0;
    readyPicker = picker => {
        assert.equal(picker.busy, true);
        assert.deepEqual(picker.items, []);
        busyShown++;
    };
    const overlappingStart = requested.length;
    const first = run('showSnippets');
    await new Promise(setImmediate);
    assert.equal(typeof release, 'function');
    const second = run('showSnippets');
    await new Promise(setImmediate);
    release();
    await Promise.all([first, second]);
    assert.equal(requested.length - overlappingStart, 1);
    assert.equal(busyShown, 2);
    assert.equal(picked.length, 4);

    const cancelled = run('showSnippets');
    await new Promise(setImmediate);
    hidePicker();
    release();
    await cancelled;
    await new Promise(setImmediate);
    assert.equal(picked.length, 4);

    const storageSnapshot = secret.get(credentialKey);
    const switched = run('showSnippets');
    await new Promise(setImmediate);
    const other = JSON.parse(storageSnapshot);
    other.tokens.access = 'another-account-access';
    secret.set(credentialKey, JSON.stringify(other));
    changedSecret({ key: credentialKey });
    release();
    await switched;
    assert.equal(picked.length, 4);
    secret.set(credentialKey, storageSnapshot);
    waitForList = undefined;

    offline = true;
    await run('showSnippets');
    assert.match(messages.at(-1), /Could not complete/);
    assert.equal(picked.length, 4);
    offline = false;

    const renewed = JSON.parse(storageSnapshot);
    renewed.tokens.expires = 0;
    secret.set(credentialKey, JSON.stringify(renewed));
    await run('showSnippets');
    assert.equal(picked.length, 5);
    revokeList = true;
    await run('showSnippets');
    assert.equal(picked.length, 5);
    assert.equal(secret.size, 0);
    assert.match(messages.at(-1), /Sign in/);
    revokeList = false;
    secret.set(credentialKey, storageSnapshot);
    await run('signOut');
    assert.equal(secret.size, 0);
    const before = requested.length;
    await run('insertSnippet');
    assert.equal(requested.length, before);
    for (const item of context.subscriptions) { item.dispose(); }
});
