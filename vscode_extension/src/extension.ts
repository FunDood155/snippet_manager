import * as vscode from 'vscode';
import { AuthClient, boundedJson, credentialKey, SaveSessionChanged, SaveUnconfirmed, SignInRequest, SignInRequired, type Snippet } from './auth';
import { buildTemplate } from './snippetTemplates';

const namespace = 'code-snippet-manager';
const configuration = () => vscode.workspace.getConfiguration('snippetManager');
const server = () => configuration().get<string>('serverUrl', '');

const languages = {
    python: 'Python', javascript: 'JavaScript', typescript: 'TypeScript', html: 'HTML', css: 'CSS',
    sql: 'SQL', json: 'JSON', shellscript: 'Shell', plaintext: 'Plain text',
};
const VS_CODE_LANGUAGE_ALIASES: Record<string, string> = {
    javascriptreact: 'javascript', typescriptreact: 'typescript', shell: 'shellscript',
};
type SnippetItem = vscode.QuickPickItem & { snippet?: Snippet };
type BrowserResult = { code: string } | 'declined' | 'expired' | 'cancelled' | 'launch-failed';

export function activate(context: vscode.ExtensionContext) {
    const auth = new AuthClient(context.secrets, server);
    const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right);
    let stopSignIn: (() => void) | undefined;
    let callback: ((uri: vscode.Uri) => void) | undefined;
    let activePicker: vscode.QuickPick<SnippetItem> | undefined;
    let checkPickerSession: (() => Promise<void>) | undefined;
    let generation = 0;
    let saving = false;

    async function updateStatus() {
        const signedIn = await auth.hasSession();
        status.text = signedIn ? '$(account) Snippo: Signed in' : '$(account) Snippo: Signed out';
        status.command = `${namespace}.${signedIn ? 'signOut' : 'signIn'}`;
        status.tooltip = signedIn ? 'Sign out of Snippo' : 'Sign in to Snippo';
        status.show();
    }

    function register(name: string, action: () => Promise<void>) {
        context.subscriptions.push(vscode.commands.registerCommand(`${namespace}.${name}`, async () => {
            try {
                await action();
            } catch (error) {
                if (error instanceof SignInRequired) {
                    void updateStatus();
                    const selection = await vscode.window.showInformationMessage('Sign in to access your snippets.', 'Sign in');
                    if (selection === 'Sign in') {
                        await vscode.commands.executeCommand(`${namespace}.signIn`);
                    }
                } else {
                    void vscode.window.showErrorMessage('Could not complete the request. Check your Snippo server and connection.');
                }
            }
        }));
    }

    function receive(attempt: SignInRequest, signal: AbortSignal): Promise<BrowserResult> {
        return new Promise((resolve) => {
            const finish = (result: BrowserResult) => {
                callback = undefined;
                clearTimeout(timer);
                signal.removeEventListener('abort', cancel);
                resolve(result);
            };
            const cancel = () => finish('cancelled');
            const timer = setTimeout(() => finish('expired'), Math.max(0, attempt.expires - Date.now()));
            callback = (uri) => {
                const code = attempt.accept(uri, vscode.env.uriScheme);
                if (code !== undefined) {
                    finish(code === null ? 'declined' : { code });
                }
            };
            signal.addEventListener('abort', cancel, { once: true });
            if (signal.aborted) {
                cancel();
            }
        });
    }

    register('signIn', async () => {
        const initialGeneration = generation;
        if (stopSignIn || await auth.hasSession() || stopSignIn || initialGeneration !== generation) {
            return;
        }
        const controller = new AbortController();
        stopSignIn = () => controller.abort();
        const signal = controller.signal;
        try {
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: 'Signing in to Snippo',
                cancellable: true,
            }, async (progress, token) => {
                const subscription = token.onCancellationRequested(() => controller.abort());
                try {
                    if (token.isCancellationRequested) {
                        return;
                    }
                    const attempt = await auth.configuration(signal);
                    if (signal.aborted) {
                        return;
                    }
                    progress.report({ message: 'Continue in your browser, then return to VS Code.' });
                    const received = receive(attempt, signal);
                    const launchFailure = new Promise<'launch-failed'>(resolve => {
                        void Promise.resolve().then(() => {
                            if (!signal.aborted) {
                                return vscode.env.openExternal(vscode.Uri.parse(attempt.url.toString()));
                            }
                        }).then(opened => {
                            if (!opened) {
                                resolve('launch-failed');
                            }
                        }, () => resolve('launch-failed'));
                    });
                    const result = await Promise.race([received, launchFailure]);
                    if (signal.aborted) {
                        return;
                    }
                    if (result === 'launch-failed') {
                        void vscode.window.showErrorMessage('Could not open the sign-in page in your browser.');
                    } else if (result === 'declined') {
                        void vscode.window.showInformationMessage('Sign-in was cancelled in the browser. You can start again.');
                    } else if (result === 'expired') {
                        void vscode.window.showInformationMessage('Sign-in expired. Start sign-in again from VS Code.');
                    } else if (typeof result === 'object') {
                        progress.report({ message: 'Finishing sign-in in VS Code…' });
                        await auth.complete(attempt, result.code, signal);
                        if (!signal.aborted) {
                            void vscode.window.showInformationMessage('Signed in to Snippo.');
                        }
                    }
                } catch (error) {
                    if (!signal.aborted) {
                        throw error;
                    }
                } finally {
                    subscription.dispose();
                }
            });
        } finally {
            controller.abort();
            stopSignIn = undefined;
            await updateStatus();
        }
    });

    register('signOut', async () => {
        generation += 1;
        stopSignIn?.();
        activePicker?.hide();
        auth.cancelLibraryReads();
        const revoked = await auth.signOut();
        await updateStatus();
        if (revoked) {
            void vscode.window.showInformationMessage('Signed out of Snippo.');
        } else {
            void vscode.window.showWarningMessage('Signed out here. The server could not confirm session revocation.');
        }
    });

    async function pickSnippets(mode: 'show' | 'search' | 'insert') {
        const initialGeneration = generation;
        const filters = new URLSearchParams({ v: '2' });
        if (mode === 'search') {
            if (!await auth.hasSession()) throw new SignInRequired();
            if (generation !== initialGeneration) return;
            const search = await vscode.window.showInputBox({ placeHolder: 'Search snippets...' });
            if (search === undefined || generation !== initialGeneration) return;
            filters.set('search', search);
        }

        activePicker?.hide();
        const picker = vscode.window.createQuickPick<SnippetItem>();
        activePicker = picker;
        checkPickerSession = undefined;
        picker.placeholder = { show: 'Select a snippet...', search: 'Search results',
            insert: 'Select a snippet to insert...' }[mode];
        picker.matchOnDescription = true;
        picker.busy = true;
        const controller = new AbortController();
        const signal = controller.signal;
        let finish: (item?: SnippetItem) => void = () => undefined;
        const selection = new Promise<SnippetItem | undefined>(resolve => { finish = resolve; });
        const listeners = [
            picker.onDidHide(() => { controller.abort(); finish(); }),
            picker.onDidAccept(() => {
                if (!picker.busy && picker.selectedItems[0]) finish(picker.selectedItems[0]);
            }),
        ];
        picker.show();
        try {
            const library = await auth.readLibrary('?' + filters.toString(), signal);
            if (signal.aborted || generation !== initialGeneration) return;
            checkPickerSession = async () => {
                if (!await library.isCurrent() && activePicker === picker) picker.hide();
            };
            await checkPickerSession();
            if (signal.aborted || generation !== initialGeneration) return;
            const recent = library.items.filter(snippet => snippet.used_at)
                .sort((a, b) => b.used_at!.localeCompare(a.used_at!) || b.sno - a.sno).slice(0, 5);
            const recentIds = new Set(recent.map(snippet => snippet.sno));
            const item = (snippet: Snippet): SnippetItem => ({
                label: snippet.name, description: [snippet.cat, snippet.language && Object.hasOwn(languages, snippet.language)
                    ? languages[snippet.language as keyof typeof languages] : undefined]
                    .filter(Boolean).join(' · '), detail: snippet.code, snippet,
            });
            picker.items = recent.length ? [
                {label: 'Recently used', kind: vscode.QuickPickItemKind.Separator},
                ...recent.map(item),
                {label: 'Library', kind: vscode.QuickPickItemKind.Separator},
                ...library.items.filter(snippet => !recentIds.has(snippet.sno)).map(item),
            ] : library.items.map(item);
            picker.busy = false;
            const selected = await selection;
            if (mode !== 'insert' || !selected?.snippet || signal.aborted || generation !== initialGeneration ||
                    !await library.isCurrent() || signal.aborted || generation !== initialGeneration) return;
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                void vscode.window.showErrorMessage('No active editor found');
                return;
            }
            const snippet = selected.snippet;
            const position = editor.selection.active;
            let inserted: boolean;
            if (snippet.template === true) {
                const template = new vscode.SnippetString();
                inserted = buildTemplate(snippet.code, template)
                    ? await editor.insertSnippet(template, position, {undoStopBefore: true, undoStopAfter: true, keepWhitespace: true})
                    : await editor.edit(builder => builder.insert(position, snippet.code));
            } else {
                inserted = await editor.edit(builder => builder.insert(position, snippet.code));
            }
            if (inserted) void library.recordUse(snippet.sno).catch(() => {});
        } catch (error) {
            if (!signal.aborted) throw error;
        } finally {
            controller.abort();
            for (const listener of listeners) listener.dispose();
            picker.dispose();
            if (activePicker === picker) {
                activePicker = undefined;
                checkPickerSession = undefined;
            }
        }
    }

    register('saveSelectedCode', async () => {
        if (saving) return;
        const editor = vscode.window.activeTextEditor;
        if (!editor || editor.selections.length !== 1 || editor.selection.isEmpty) {
            void vscode.window.showInformationMessage('Select one nonempty block of code to save to Snippo.');
            return;
        }
        const languageId = editor.document.languageId;
        const code = editor.document.getText(editor.selection);
        if (!code.trim()) {
            void vscode.window.showInformationMessage('The selected code is blank.');
            return;
        }
        if (Buffer.byteLength(JSON.stringify(code), 'utf8') >= 1024 * 1024) {
            void vscode.window.showWarningMessage('The selected code is too large to save to Snippo.');
            return;
        }

        saving = true;
        const initialGeneration = generation;
        const isCurrent = () => generation === initialGeneration;
        const checkCurrent = () => {
            if (!isCurrent()) throw new SaveSessionChanged();
        };
        let dispose: (() => void) | undefined;
        try {
            const draft = await auth.prepareSnippetSave(isCurrent);
            dispose = draft.dispose;
            const required = (value: string) => value.trim() ? undefined : 'Enter a value.';
            const name = await vscode.window.showInputBox({prompt: 'Snippet name', validateInput: required});
            if (name === undefined) return;
            checkCurrent();
            const cat = await vscode.window.showInputBox({prompt: 'Category', validateInput: required});
            if (cat === undefined) return;
            checkCurrent();
            const suggested = VS_CODE_LANGUAGE_ALIASES[languageId] ?? languageId;
            const options = [{label: 'Unspecified', id: ''}, ...Object.entries(languages)
                .map(([id, label]) => ({label: id === suggested ? label + ' (editor language)' : label, id}))];
            options.sort((a, b) => Number(b.id === suggested) - Number(a.id === suggested));
            const language = await vscode.window.showQuickPick(options, {placeHolder: 'Choose a language'});
            if (!language) return;
            checkCurrent();
            const confirmed = await vscode.window.showWarningMessage('Save selected code to your Snippo account?', {
                modal: true, detail: 'Only the selected text will be sent to your configured Snippo server.',
            }, 'Save');
            if (confirmed !== 'Save') return;
            checkCurrent();

            const response = await draft.save({name, cat, code, language: language.id});
            if (response.status === 201) {
                const body = await boundedJson(response, 2 * 1024 * 1024).catch(() => undefined) as {language?: unknown} | undefined;
                if (language.id && !body?.language) {
                    void vscode.window.showWarningMessage('Snippet saved. This server did not save its language.');
                } else {
                    void vscode.window.showInformationMessage('Snippet saved to Snippo.');
                }
            } else {
                const message = {
                    400: 'The server rejected the snippet fields.',
                    409: 'A snippet with that name already exists.',
                    422: 'Your library storage limit was reached. Delete a personal snippet or reduce its size.',
                    413: 'The snippet is too large to save.',
                    429: 'Snippo is busy. Try again later.',
                }[response.status] ?? 'Snippo could not confirm the save. Check your library before trying again.';
                void vscode.window.showWarningMessage(message);
            }
        } catch (error) {
            if (error instanceof SignInRequired) throw error;
            const message = error instanceof SaveSessionChanged
                ? 'Your Snippo session or server changed. No code was sent. Run Save Selected Code again.'
                : error instanceof SaveUnconfirmed
                    ? 'Snippo could not confirm the save. Check your library before trying again.'
                    : 'Could not check your Snippo session. No code was sent. Check your connection and try again.';
            void vscode.window.showWarningMessage(message);
        } finally {
            dispose?.();
            saving = false;
        }
    });

    register('showSnippets', () => pickSnippets('show'));
    register('searchSnippets', () => pickSnippets('search'));
    register('insertSnippet', () => pickSnippets('insert'));
    context.subscriptions.push(
        status,
        vscode.window.registerUriHandler({ handleUri: uri => callback?.(uri) }),
        context.secrets.onDidChange(event => {
            if (event.key === credentialKey) {
                void checkPickerSession?.();
                void updateStatus();
            }
        }),
        vscode.workspace.onDidChangeConfiguration(event => {
            if (event.affectsConfiguration('snippetManager.serverUrl')) {
                generation += 1;
                stopSignIn?.();
                activePicker?.hide();
                auth.cancelLibraryReads();
                void updateStatus();
            }
        }),
        { dispose: () => { stopSignIn?.(); activePicker?.hide(); auth.cancelLibraryReads(); } },
    );
    void updateStatus();
}
