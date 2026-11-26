import * as vscode from 'vscode';
import { AuthClient, credentialKey, SignInRequest, SignInRequired } from './auth';

const namespace = 'code-snippet-manager';
const configuration = () => vscode.workspace.getConfiguration('snippetManager');
const server = () => configuration().get<string>('serverUrl', '');

type Snippet = { name: string; cat: string; code: string };
type BrowserResult = { code: string } | 'declined' | 'expired' | 'cancelled' | 'launch-failed';

export function activate(context: vscode.ExtensionContext) {
    const auth = new AuthClient(context.secrets, server);
    const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right);
    let stopSignIn: (() => void) | undefined;
    let callback: ((uri: vscode.Uri) => void) | undefined;
    let activePicker: vscode.CancellationTokenSource | undefined;
    let generation = 0;

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
        activePicker?.cancel();
        const revoked = await auth.signOut();
        await updateStatus();
        if (revoked) {
            void vscode.window.showInformationMessage('Signed out of Snippo.');
        } else {
            void vscode.window.showWarningMessage('Signed out here. The server could not confirm session revocation.');
        }
    });

    async function pickSnippets(mode: 'show' | 'search' | 'insert') {
        if (!await auth.hasSession()) {
            throw new SignInRequired();
        }
        const initialGeneration = generation;
        let query = '';
        if (mode === 'search') {
            const search = await vscode.window.showInputBox({ placeHolder: 'Search snippets...' });
            if (search === undefined || generation !== initialGeneration) {
                return;
            }
            query = '?' + new URLSearchParams({ search }).toString();
        }
        const response = await auth.request('/api/snippets' + query);
        const snippets = await response.json() as Snippet[];
        if (generation !== initialGeneration) {
            return;
        }
        activePicker?.cancel();
        const cancellation = new vscode.CancellationTokenSource();
        activePicker = cancellation;
        try {
            const items = snippets.map(snippet => ({
                label: snippet.name, description: snippet.cat, detail: snippet.code, code: snippet.code,
            }));
            const selected = await vscode.window.showQuickPick(items, {
                placeHolder: { show: 'Select a snippet...', search: 'Search results', insert: 'Select a snippet to insert...' }[mode],
            }, cancellation.token);
            if (mode !== 'insert' || !selected || cancellation.token.isCancellationRequested ||
                    generation !== initialGeneration) {
                return;
            }
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                void vscode.window.showErrorMessage('No active editor found');
                return;
            }
            await editor.edit(builder => builder.insert(editor.selection.active, selected.code));
        } finally {
            cancellation.dispose();
            if (activePicker === cancellation) {
                activePicker = undefined;
            }
        }
    }

    register('showSnippets', () => pickSnippets('show'));
    register('searchSnippets', () => pickSnippets('search'));
    register('insertSnippet', () => pickSnippets('insert'));
    context.subscriptions.push(
        status,
        vscode.window.registerUriHandler({ handleUri: uri => callback?.(uri) }),
        context.secrets.onDidChange(event => {
            if (event.key === credentialKey) {
                void updateStatus();
            }
        }),
        vscode.workspace.onDidChangeConfiguration(event => {
            if (event.affectsConfiguration('snippetManager.serverUrl')) {
                generation += 1;
                stopSignIn?.();
                activePicker?.cancel();
                void updateStatus();
            }
        }),
        { dispose: () => { stopSignIn?.(); activePicker?.cancel(); } },
    );
    void updateStatus();
}
