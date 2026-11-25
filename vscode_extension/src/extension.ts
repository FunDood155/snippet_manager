import * as vscode from 'vscode';
import { AuthClient, credentialKey, SignInRequest, SignInRequired } from './auth';

const namespace = 'code-snippet-manager';
const configuration = () => vscode.workspace.getConfiguration('snippetManager');
const server = () => configuration().get<string>('serverUrl', '');

type Snippet = { name: string; cat: string; code: string };

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

    function receive(attempt: SignInRequest, token: vscode.CancellationToken): Promise<string | null> {
        return new Promise((resolve) => {
            const finish = (code: string | null) => {
                callback = undefined;
                clearTimeout(timer);
                subscription.dispose();
                resolve(code);
            };
            const timer = setTimeout(() => finish(null), Math.max(0, attempt.expires - Date.now()));
            const subscription = token.onCancellationRequested(() => finish(null));
            callback = (uri) => {
                const code = attempt.accept(uri, vscode.env.uriScheme);
                if (code !== undefined) {
                    finish(code);
                }
            };
            stopSignIn = () => finish(null);
            if (token.isCancellationRequested) {
                finish(null);
            }
        });
    }

    register('signIn', async () => {
        if (stopSignIn || await auth.hasSession() || stopSignIn) {
            return;
        }
        const controller = new AbortController();
        stopSignIn = () => controller.abort();
        const initialGeneration = generation;
        try {
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: 'Signing in to Snippo',
                cancellable: true,
            }, async (_progress, token) => {
                const subscription = token.onCancellationRequested(() => controller.abort());
                try {
                    const attempt = await auth.configuration();
                    if (controller.signal.aborted || initialGeneration !== generation || token.isCancellationRequested) {
                        return;
                    }
                    const received = receive(attempt, token);
                    if (!await vscode.env.openExternal(vscode.Uri.parse(attempt.url.toString()))) {
                        stopSignIn?.();
                        void vscode.window.showErrorMessage('Could not open the sign-in page in your browser.');
                        return;
                    }
                    const code = await received;
                    stopSignIn = () => controller.abort();
                    if (code && !token.isCancellationRequested && initialGeneration === generation) {
                        try {
                            await auth.complete(attempt, code, controller.signal);
                        } catch (error) {
                            if (!controller.signal.aborted) {
                                throw error;
                            }
                        }
                        if (!controller.signal.aborted) {
                            void vscode.window.showInformationMessage('Signed in to Snippo.');
                        }
                    } else if (!token.isCancellationRequested && initialGeneration === generation) {
                        void vscode.window.showInformationMessage('Sign-in was declined or expired. You can start again.');
                    }
                } finally {
                    subscription.dispose();
                }
            });
        } finally {
            stopSignIn?.();
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
