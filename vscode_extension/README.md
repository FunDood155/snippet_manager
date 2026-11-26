# Snippo

**Your code. Always within reach.**

Snippo connects VS Code Desktop to your private web snippet library. Save a snippet on the web, then find and insert it without leaving your editor.

**Publisher** · Dinesh Kaarthik (`dineshkaarthik`)

## Get started

1. Install `snippo-1.0.0.vsix` using **Extensions: Install from VSIX...** in the VS Code Command Palette. This package is a release candidate for private testing.
2. If you used the previous Code Snippet Manager extension, disable or uninstall it. Snippo has its own secure storage and requires a fresh sign-in. Your server-side snippets stay with your account.
3. Run **Snippo: Sign In**. Sign in or create an account in the browser, approve access, and select **Open VS Code** or **Open VS Code Insiders** on the callback page.
4. Add, filter, and delete snippets in the [web library](https://snippet-manager-tan.vercel.app).

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
- There is no account self-delete screen. To arrange account and associated data deletion, contact the maintainer through your private testing channel. Do not put your account email, tokens, or snippet content in a public issue. A formal retention and deletion policy remains to be established for public distribution.

## Known limitations

- Snippo depends on an available Flask server and Supabase Auth. The default URL can be restricted during private testing, and the backend must support the `dineshkaarthik.snippo` callback before the new extension can sign in.
- VS Code for the Web and offline snippet access are outside the current supported flow. Use the web library to manage snippets.
- Email ownership is not verified in the current private-test configuration. Password recovery is currently unavailable in the web app. Use a test address you control.
- If the extension cannot reach the server when signing out, it clears local credentials and reports that server revocation could not be confirmed. Use web revocation when the server is available.

Report bugs at [GitHub Issues](https://github.com/FunDood155/snippet_manager/issues). Include the extension version and reproduction steps with sensitive details removed.

## License

Snippo is licensed under the [MIT License](https://opensource.org/license/mit). The full license and copyright notice are included in the VSIX.
