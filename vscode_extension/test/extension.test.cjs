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
    let inserted;
    let handleUri;
    let cancelProgress;
    let openBrowser;
    const disposable = () => ({ dispose() {} });
    class Cancellation {
        token = { isCancellationRequested: false };
        cancel() { this.token.isCancellationRequested = true; }
        dispose() {}
    }
    const vscode = {
        commands: {
            registerCommand(name, callback) { commands.set(name, callback); return disposable(); },
            executeCommand: name => commands.get(name)(),
        },
        env: {
            uriScheme: 'vscode',
            openExternal: async uri => { await openBrowser(uri); return true; },
        },
        Uri: { parse: value => new URL(value) },
        StatusBarAlignment: { Right: 2 },
        ProgressLocation: { Notification: 3 },
        CancellationTokenSource: Cancellation,
        workspace: { getConfiguration: () => ({ get: () => origin }), onDidChangeConfiguration: disposable },
        window: {
            createStatusBarItem: () => ({ show() {}, dispose() {} }),
            registerUriHandler: handler => { handleUri = handler.handleUri; return disposable(); },
            showInformationMessage: async message => { messages.push(message); },
            showWarningMessage: async message => { messages.push(message); },
            showErrorMessage: async message => { messages.push(message); },
            showInputBox: async () => 'cat + &',
            showQuickPick: async items => { picked.push(items); return items[0]; },
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
                return callback({}, token);
            },
        },
    };
    const context = {
        subscriptions: [],
        secrets: {
            get: async key => secret.get(key),
            store: async (key, value) => { secret.set(key, value); },
            delete: async key => { secret.delete(key); },
            onDidChange: disposable,
        },
    };
    t.mock.method(global, 'fetch', async (url, init) => {
        const target = new URL(url);
        requested.push(target);
        if (target.pathname === '/oauth/vscode/config') { return Response.json(config); }
        if (target.pathname.endsWith('/token')) {
            assert.equal(init.body.get('code'), 'browser-fixture');
            assert.ok(init.body.get('code_verifier'));
            return Response.json({ access_token: 'access', refresh_token: 'refresh', expires_in: 3600 });
        }
        assert.equal(init.headers.Authorization, 'Bearer access');
        if (target.pathname.endsWith('/logout')) { return new Response(null, { status: 204 }); }
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
    assert.equal(requested.filter(request => request.pathname.endsWith('/token')).length, 1);

    await run('showSnippets');
    await run('searchSnippets');
    await run('insertSnippet');
    assert.equal(picked.length, 3);
    assert.equal(picked[0][0].label, 'Snippet fixture');
    assert.equal(requested.find(request => request.search).searchParams.get('search'), 'cat + &');
    assert.equal(inserted, 'print(5)');

    await run('signOut');
    assert.equal(secret.size, 0);
    const before = requested.length;
    await run('insertSnippet');
    assert.equal(requested.length, before);
    for (const item of context.subscriptions) { item.dispose(); }
});
