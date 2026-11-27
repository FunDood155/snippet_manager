# Snippo

**Your code. Always within reach.**

Snippo connects VS Code Desktop to your private web snippet library. Save a snippet on the web, then find and insert it without leaving your editor.

**Publisher** · Dinesh Kaarthik (`dineshkaarthik`)

## Get started

1. If you installed the private-test Snippo extension (`dineshkaarthik.snippo`), uninstall it first. Remove the older Code Snippet Manager extension too if you still have it installed.
2. Install **Snippo - Code Snippets**. To install from the package file, choose **Extensions: Install from VSIX...** in the Command Palette and select `snippo-code-snippets-1.0.0.vsix`. Reload VS Code after replacing an older extension.
3. Run **Snippo: Sign In** and use the browser to sign in and approve access. If you create an account, verify your email and then start **Snippo: Sign In** again. After approval, allow the browser to open VS Code. If it stays on the callback page, choose **Open VS Code** or **Open VS Code Insiders** for the editor you started from.
4. Add, filter, and delete snippets in the [web library](https://snippet-manager-tan.vercel.app).

Sign in again after upgrading from a private-test build. VS Code scopes SecretStorage to the extension ID. Use your existing Snippo account to access your saved snippets.

The extension needs VS Code Desktop or Insiders compatible with `^1.137.0`, a browser, internet access for hosted use, and a working Snippo backend with Supabase Auth. A maintainer may configure the `snippetManager.serverUrl` user setting for a test backend. Use HTTPS for hosted servers. HTTP is supported on loopback for local development.

## Commands

| Command | What it does |
| --- | --- |
| **Snippo: Sign In** | Connects VS Code to your account using browser authorization. |
| **Snippo: Show Snippets** | Opens your snippet list. |
| **Snippo: Search Snippets** | Searches your library by name or code. |
| **Snippo: Insert Snippet** | Inserts your selected snippet at the cursor in the active editor. |
| **Snippo: Sign Out** | Clears local credentials and requests revocation of this extension session. |

Individual snippets can be deleted in the web library. Account-wide VS Code access can be revoked from the same web interface when OAuth is configured.

## Data and privacy

- Supabase Auth receives the email address and the application password entered on the website. Supabase manages the password and account. Authentication is required to use the hosted service.
- Snippet names, categories, code, and account identifiers are stored in PostgreSQL through the Flask service. The extension sends your search text to that service and receives the matching snippets. Avoid storing or pasting API keys, passwords, or other secrets in snippets.
- The extension stores access and refresh tokens in VS Code SecretStorage. It uses them to authenticate requests and renew its session. The website stores session tokens on the server and uses an opaque browser session cookie. Signing out does not delete your account or your snippets.
- To request permanent deletion of your account and its owned snippets, use **Request account deletion** in the web library or email [snippo.support@gmail.com](mailto:snippo.support@gmail.com) from the address on your account. Support verifies ownership and asks for explicit consent. Keep passwords, verification links, codes, tokens and snippet contents out of the request.

## Known limitations

- Snippo depends on an available Flask server and Supabase Auth. If you configure a custom backend, it must support the `dineshkaarthik.snippo-code-snippets` callback.
- VS Code for the Web and offline snippet access are outside the current supported flow. Use the web library to manage snippets.
- Snippo requires email verification and supports password recovery in the web app. Email delivery depends on the backend's email configuration.
- If the extension cannot reach the server when signing out, it clears local credentials and reports that server revocation could not be confirmed. Use web revocation when the server is available.

Report bugs at [GitHub Issues](https://github.com/FunDood155/snippet_manager/issues). Include the extension version and reproduction steps with sensitive details removed.

## License

Snippo is licensed under the [MIT License](https://opensource.org/license/mit). The full license and copyright notice are included in the VSIX.
