import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext) {

	const disposable = vscode.commands.registerCommand(
		'code-snippet-manager.showSnippets',
		async () => {

			try {
				const response = await fetch(
					'http://127.0.0.1:5000/api/snippets'
				);

				const data = await response.json() as any[];

				const snippets = data.map(snippet => ({
					label: snippet.name,
					description: snippet.cat,
					detail: snippet.code
				}));

				await vscode.window.showQuickPick(
					snippets,
					{
						placeHolder: 'Select a snippet...'
					}
				);

			} catch (error) {
				console.error(error);

				vscode.window.showErrorMessage(
					'Could not connect to Flask API'
				);
			}
		}
	);

	context.subscriptions.push(disposable);


	const searchDisposable = vscode.commands.registerCommand(
		'code-snippet-manager.searchSnippets',
		async () => {

			const search = await vscode.window.showInputBox({
				placeHolder: 'Search snippets...'
			});

			if (search === undefined) {
				return;
			}

			try {
				const response = await fetch(
					`http://127.0.0.1:5000/api/snippets?search=${encodeURIComponent(search)}`
				);

				const data = await response.json() as any[];

				const snippets = data.map(snippet => ({
					label: snippet.name,
					description: snippet.cat,
					detail: snippet.code
				}));

				await vscode.window.showQuickPick(
					snippets,
					{
						placeHolder: 'Search results'
					}
				);

			} catch (error) {
				console.error(error);

				vscode.window.showErrorMessage(
					'Could not connect to Flask API'
				);
			}
		}
	);

	context.subscriptions.push(searchDisposable);

	const insertDisposable = vscode.commands.registerCommand(
    'code-snippet-manager.insertSnippet',
    async () => {

        try {
            const response = await fetch(
                'http://127.0.0.1:5000/api/snippets'
            );

            const data = await response.json() as any[];

            const snippets = data.map(snippet => ({
                label: snippet.name,
                description: snippet.cat,
                detail: snippet.code,
                code: snippet.code
            }));

            const selected = await vscode.window.showQuickPick(
                snippets,
                {
                    placeHolder: 'Select a snippet to insert...'
                }
            );

            if (!selected) {
                return;
            }

            const editor = vscode.window.activeTextEditor;

            if (!editor) {
                vscode.window.showErrorMessage(
                    'No active editor found'
                );
                return;
            }

            editor.edit(editBuilder => {
                editBuilder.insert(
                    editor.selection.active,
                    selected.code
                );
            });

        } catch (error) {
            console.error(error);

            vscode.window.showErrorMessage(
                'Could not connect to Flask API'
            );
        }
    }
);

context.subscriptions.push(insertDisposable);
}

export function deactivate() {}