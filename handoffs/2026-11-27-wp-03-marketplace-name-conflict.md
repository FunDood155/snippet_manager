# WP-03 — Resolve Marketplace name conflict

ID: SNIPPO-WP03-MARKETPLACE-NAME
Repository: FunDood155/snippet_manager
Verified source: main at 0551a2c8ba50e81b1976a89819e845fcfb3fed72
Implementation branch: main (direct scoped commit; reconcile latest head first)
Commit message: resolve marketplace name conflict

## Objective
Marketplace rejected the initial VSIX because snippo already exists. Use name `snippo-code-snippets`, displayName `Snippo - Code Snippets`, publisher `dineshkaarthik`, version `1.0.0`. Keep Snippo branding, Hippo icon, tagline, website, database and app features. Public search did not reveal an exact proposed name match, but availability is not guaranteed (including reserved names); user will retry manual upload. Microsoft docs require uniqueness for name and display name: https://code.visualstudio.com/api/working-with-extensions/publishing-extension.

## Scope
- Change name/displayName in vscode_extension/package.json, synchronize root name entries in package-lock.json without unrelated dependency upgrades.
- Change the extension authority in vscode_extension/src/auth.ts and both fixed vscode:// and vscode-insiders:// links in templates/vscode_callback.html to dineshkaarthik.snippo-code-snippets. Search current tracked source, tests and documentation for all old identity and package filename references; update relevant active references (not historical handoffs). Baseline tests/test_authentication.py and vscode_extension/test/auth.test.cjs contain explicit old IDs. Update build/install examples and explain that users must uninstall old private-test extension and sign in again under new identity; VS Code SecretStorage is scoped to extension ID. Correct stale private-testing install wording in extension README for public package without making unverified privacy/compliance claims.
- Preserve internal command IDs, settings, OAuth HTTPS redirect URI, provider client ID, state/PKCE, scheme/authority/path validation, automatic callback and manual fallback, session/revocation and ownership checks. No arbitrary callback target or security relaxation. No database migrations, SMTP or Vercel configuration changes, no unrelated UI changes, no Marketplace upload.
- Run backend and extension regression suites, compile and package clean VSIX (npm ci, npm test, npm run package); verify embedded manifest, VSIX identity, icon, compiled callback authority and expected filename snippo-code-snippets-1.0.0.vsix. Report exact test results and provide package to user if feasible. Do not commit generated VSIX or dependencies.
- Commit/push scoped changes directly to main (no new branch/merge); verify automatic Vercel Production deployment of exact commit and updated stable/Insiders links. If automatic deployment fails, report blocker rather than changing settings or manually deploying.
- User installs new VSIX after removing old extension and reloads VS Code, tests browser-to-editor sign-in and snippet insertion before manually retrying upload. Publication remains user-controlled. Existing privacy notice/release gate review remains outstanding; do not certify it completed.

## Acceptance/report
Correct manifest/lockfile, new callback authority on both sides, unchanged security/branding/data, targeted tests/build pass, package inspected, Production exact commit verified, report actual commit/files/tests/VSIX location and remaining blockers. No database writes or Marketplace publication.
