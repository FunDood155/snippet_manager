# WP-03 — Temporary Snippo extension icon

ID: SNIPPO-WP03-ICON
Repository: FunDood155/snippet_manager
Verified baseline: main at 1372b57c23336fb419e737e1605493005d9fc45a
Implementation branch: main (release icon only; reconcile latest head first).
Commit message: add snippo extension icon

Use the prepared snippo-icon.png attached by the user to the Work chat. It is the approved Hippo face crop with no text, 256 x 256 PNG. SHA-256: b2519526d488d2ecfe39b3f6d9a7b9d1b92c8dc8569ef50f1722bf6002294a8e. If missing, report the attachment blocker. Do not substitute different artwork.

- Add the exact PNG at vscode_extension/images/icon.png; set the top-level icon property in vscode_extension/package.json to images/icon.png. Keep version 1.0.0, publisher dineshkaarthik, name snippo, command IDs, OAuth identity and all other manifest properties unchanged.
- Verify .vscodeignore includes the asset. Run npm ci, npm test and npm run package where possible. Inspect packaged VSIX for icon and manifest path; keep generated VSIX and dependencies out of Git. Report tests not run.
- Commit and push only these two files to main after checking diff (unless a narrowly justified inclusion fix is needed). No database writes, application behavior changes, Vercel configuration changes, manual deployment or Marketplace upload. Existing automatic deployment may be triggered by main push; inspect and report actual result.
- Future icon changes replace the PNG and increment release version, retaining extension identity. Confirm artwork rights for public distribution if uncertain.
- Report commit SHA, file paths, exact tests/package results, icon inclusion, automatic deployment if triggered, and any blockers. Public publication remains separate.
