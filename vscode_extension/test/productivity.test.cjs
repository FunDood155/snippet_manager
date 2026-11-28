const assert = require('node:assert/strict');
const Module = require('node:module');
const { test } = require('node:test');
const { buildTemplate, templateParts } = require('../out/snippetTemplates.js');

test('only bounded named fields become native placeholders; all other text is literal', () => {
    const calls = [];
    const builder = {
        appendText: text => calls.push(['literal', text]),
        appendPlaceholder: (name, number) => calls.push(['field', name, number]),
        appendTabstop: number => calls.push(['stop', number]),
    };
    const first = '  $HOME ${TM_FILENAME} \\ ';
    assert.equal(buildTemplate(first + '{{name}}\t{{other}} {{name}}\r\n', builder), true);
    assert.deepEqual(calls.filter(call => call[0] === 'field'),
                     [['field', 'name', 1], ['field', 'other', 2], ['field', 'name', 1]]);
    assert.equal(calls[0][1], first);
    assert.deepEqual(calls.at(-1), ['stop', 0]);
    for (const code of ['plain', '{{bad-name}}', '{{a}} {{', '{{{name}}}', '{{' + 'x'.repeat(25) + '}}', '{{a}}'.repeat(21)]) {
        assert.equal(templateParts(code), undefined);
    }
});

test('save and insert respect selection, consent, server results, and successful-use tracking', async t => {
    const origin = 'https://snippets.example.test';
    const stored = JSON.stringify({
        origin, config: {provider: 'https://auth.example.test', clientId: 'fixture', redirectUri: origin + '/oauth/vscode/callback'},
        tokens: {access: 'fixture-access', refresh: 'fixture-refresh', expires: Date.now() + 300000},
    });
    const commands = new Map();
    const requests = [];
    const messages = [];
    const code = '  \tprint("$HOME \\ test")\r\n';
    const range = {isEmpty: false, active: 0};
    let input = [];
    let selectedLanguage;
    let confirmation;
    let saveStatus = 201;
    let failSave = false;
    let editingSucceeded = true;
    let inserted;
    let template = false;
    let releaseRecent;
    let showed;
    let selectionCode = code;
    const dispos = () => ({dispose() {}});
    const editor = {
        selection: range, selections: [range],
        document: {
            languageId: 'python',
            getText(selection) { assert.equal(selection, range); return selectionCode; },
        },
        async edit(callback) {
            callback({insert: (position, value) => { assert.equal(position, 0); inserted = value; }});
            return editingSucceeded;
        },
        async insertSnippet(value, position, options) {
            assert.equal(position, 0);
            assert.equal(options.keepWhitespace, true);
            inserted = value.parts;
            return editingSucceeded;
        },
    };
    const vscode = {
        StatusBarAlignment: {Right: 1},
        QuickPickItemKind: {Separator: -1},
        SnippetString: class {
            parts = [];
            appendText(text) { this.parts.push(text); }
            appendPlaceholder(name, n) { this.parts.push([name, n]); }
            appendTabstop(n) { this.parts.push(n); }
        },
        commands: {registerCommand(name, callback) { commands.set(name, callback); return dispos(); }},
        workspace: {getConfiguration: () => ({get: () => origin}), onDidChangeConfiguration: dispos},
        window: {
            activeTextEditor: editor,
            createStatusBarItem: () => ({...dispos(), show() {}}),
            registerUriHandler: dispos,
            showInformationMessage: async text => { messages.push(text); },
            showWarningMessage: async (text, options) => {
                messages.push(text);
                return options?.modal ? confirmation : undefined;
            },
            showErrorMessage: async text => { messages.push(text); },
            showInputBox: async () => input.shift(),
            showQuickPick: async options => {
                assert.equal(options[0].id, 'python');
                assert.match(options[0].label, /editor language/);
                return options.find(option => option.id === selectedLanguage);
            },
            createQuickPick() {
                let accept;
                let hide;
                return {
                    set items(rows) {
                        showed = rows;
                        this.selectedItems = rows.filter(row => row.snippet).slice(0, 1);
                        queueMicrotask(() => accept());
                    },
                    onDidHide(fn) { hide = fn; return dispos(); },
                    onDidAccept(fn) { accept = fn; return dispos(); },
                    show() {},
                    hide() { hide(); },
                    dispose() {},
                };
            },
        },
    };
    t.mock.method(global, 'fetch', async (url, init) => {
        const path = new URL(url);
        assert.equal(init.headers.Authorization, 'Bearer fixture-access');
        requests.push([path.pathname, init.method, init.body]);
        if (path.pathname.endsWith('/recent')) {
            return new Promise(resolve => {releaseRecent = () => resolve(new Response(null, {status: 204}));});
        }
        assert.equal(path.searchParams.get('v'), '2');
        if (init.method === 'POST') {
            if (failSave) throw new Error('Network failure');
            return Response.json({language: 'python'}, {status: saveStatus});
        }
        return Response.json([
            {sno: 20, name: 'Later in picker', cat: 'Other', language: 'sql', code: 'SELECT 1'},
            {sno: 10, name: 'Recent target', cat: 'Fixture', language: 'python', used_at: '2026-11-28T00:00:00Z',
                code: template ? '  $HOME {{name}} {{name}}\n' : code, template},
        ]);
    });
    const load = Module._load;
    const mock = t.mock.method(Module, '_load', (name, ...args) => name === 'vscode' ? vscode : load(name, ...args));
    const { activate } = require('../out/extension.js');
    mock.mock.restore();
    const context = { subscriptions: [], secrets: {get: async () => stored, onDidChange: dispos} };
    activate(context);
    const run = name => commands.get('code-snippet-manager.' + name)();

    editor.selections = [range, range];
    await run('saveSelectedCode');
    assert.match(messages.at(-1), /one nonempty/);
    editor.selections = [range];
    selectionCode = '  \n';
    await run('saveSelectedCode');
    assert.match(messages.at(-1), /blank/);
    selectionCode = code;
    for (const prompts of [[], ['Name'], ['Name', 'Category']]) {
        input = prompts;
        await run('saveSelectedCode');
    }
    selectedLanguage = 'python';
    input = ['Name', 'Category'];
    await run('saveSelectedCode');
    assert.equal(requests.length, 0);

    confirmation = 'Save';
    input = ['Name', 'Category'];
    await run('saveSelectedCode');
    assert.deepEqual(JSON.parse(requests[0][2]), {name: 'Name', cat: 'Category', code, language: 'python'});
    assert.match(messages.at(-1), /saved to Snippo/);
    input = ['Name', 'Category'];
    saveStatus = 409;
    await run('saveSelectedCode');
    assert.match(messages.at(-1), /already exists/);
    input = ['Name', 'Category'];
    failSave = true;
    await run('saveSelectedCode');
    assert.match(messages.at(-1), /could not confirm/);
    assert.equal(requests.length, 3);

    editingSucceeded = false;
    await run('insertSnippet');
    assert.equal(inserted, code);
    assert.equal(requests.filter(row => row[0].endsWith('/recent')).length, 0);
    assert.deepEqual(showed.map(item => item.label), ['Recently used', 'Recent target', 'Library', 'Later in picker']);

    template = true;
    editingSucceeded = true;
    await run('insertSnippet');
    assert.deepEqual(inserted, ['  $HOME ', ['name', 1], ' ', ['name', 1], '\n', 0]);
    await new Promise(setImmediate);
    assert.equal(requests.filter(row => row[0].endsWith('/recent')).length, 1);
    assert.equal(typeof releaseRecent, 'function');
    releaseRecent();
});

test('save command is contextual and keyboard shortcuts stay user-configurable', () => {
    const { contributes } = require('../package.json');
    const save = contributes.commands.find(item => item.command.endsWith('.saveSelectedCode'));
    const menu = contributes.menus['editor/context'].find(item => item.command === save.command);
    assert.equal(menu.when, 'editorHasSelection && !editorHasMultipleSelections');
    assert.equal(save.enablement, menu.when);
    assert.equal(contributes.keybindings, undefined);
});
