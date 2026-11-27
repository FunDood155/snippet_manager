# WP-06 — Web UI redesign and usability improvements

**ID:** SNIPPO-WP06-WEB-UI
**Status:** Ready for Work
**Repository:** FunDood155/snippet_manager
**Publication branch:** features/handoffs (documentation only)
**Reviewed baseline:** main 5d543d8d8cd2dc2149abf9b35af758aed7e43322; reconcile latest main before implementation.
**Implementation branch:** create feature/ui-usability from latest main.
**Commit message:** improve web ui and usability

## Objective and visual reference

Replace the oversized, low-contrast authenticated library with a compact, responsive Snippo dashboard. Use the two screenshots supplied by the user with Work Authorization: the proposed dark dashboard (target layout) and the current Code Snippet Manager page (before reference). The user will attach both to Work; these are not committed assets. Follow the proposed image for composition, spacing, controls and hierarchy, not as a literal fixed-size bitmap. Use VS Code blue **#007ACC** as the primary accent, with accessible text/hover/focus contrast. Keep a cohesive dark palette compatible with existing auth pages. Use the existing hippo icon at vscode_extension/images/icon.png as the source for a web-only logo asset; do not alter the extension asset. Replace the oversized black Code Snippet Manager heading and old browser title with Snippo branding, logo plus name at top left, and a readable Snippet Library heading. No new design framework or paid assets.

## Scope — ten approved improvements

1. Compact top navigation/header with Snippo branding and contrast fixes as above.
2. Combined compact search input and category dropdown; search, category and snippet-type selections work together, retain state on navigation and allow clearing. Keep server-side search/filter semantics, no unnecessary requests.
3. New Snippet button toggles a compact add form, closed initially. Provide accessible labels, cancel/close and validation; preserve entered fields on recoverable save errors. Keep existing save behavior and protection.
4. Account dropdown at top right for Sign out, Revoke all VS Code sessions and Request account deletion. Retain existing POST/CSRF and routes; session revocation requires a clear confirmation. No new account profile feature.
5. Compact dark snippet cards with readable code, name, category and clear shared/personal distinction. Code stays escaped and whitespace-preserving; long lines scroll within code blocks, not the page. Personal action menu contains Delete; shared action contains Hide, never global Delete.
6. Responsive desktop, laptop, tablet and phone layout; controls wrap naturally, readable spacing, keyboard focus and accessible menu/disclosure states. Include viewport metadata. No giant permanent forms.
7. Visible All / Personal / Defaults filters. All = personal + visible shared; Personal = current user's personal rows; Defaults = visible shared only. Combine with category/search and show a useful no-results state.
8. Explicit confirmation before personal snippet deletion; cancel is non-destructive. Keep server ownership checks and existing deletion semantics.
9. Small non-blocking top-right success/error toasts, approximately three seconds for ordinary success, dismissible; accessible live region, meaningful validation/service error handling, no secret/internal exception exposure. Never show success for failed operations. Include add/delete/hide/restore and relevant account actions where feasible.
10. Per-account hide and restore of individual shared defaults, plus restore-all. Provide a clearly discoverable hidden-defaults management view/control even when all defaults are hidden. Hiding never removes the shared record or affects another account. Persist across sessions/devices and apply to normal website and existing VS Code API list/search results; hidden IDs should not be returned by the normal detail endpoint. New shared defaults are visible by default.

Likely files: templates/index.html, static/style.css, a small same-origin dashboard JS file, main.py, store.py, relevant tests, one new Supabase migration and documentation, web logo asset. Inspect shared CSS usage and isolate dashboard styles to avoid auth regressions. Respect existing CSP; narrowly allow the dashboard's same-origin script if needed, never unsafe-inline/eval. Keep forms usable with server-side validation and CSRF; do not expose user IDs in client-supplied ownership parameters.

## Hide/restore data design and security

Add a small private or appropriately RLS-protected hidden_default_snippets relation with composite primary key (user_id, snippet_id), FK to auth.users(id) and public.default_snippets(sno), both ON DELETE CASCADE for preference cleanup only. Use existing verified owner context and narrowly scoped snippet_app permissions, RLS SELECT/INSERT/DELETE policies matching that owner, no broad Data API access, no UPDATE needed. User identity always derived from session/token. Parameterized queries and idempotent hide/restore; validate target is an existing shared ID, not a personal row. Restore-all only deletes that owner's preference rows; never deletes snippets. Existing users start with no preferences. Retain reserved shared ID range, personal ownership predicates, FK, sequence, shared SELECT-only behavior, account-deletion runbook and API numeric sno/name/cat/code contract. No duplicate code storage, no user data cleanup or account changes. Preserve one-time OAuth launch patch, login, registration, email verification, CSRF, session revocation and extension sign-in. Add migration rather than rewriting applied history. Document additive schema-first deployment prerequisite and rollback compatibility.

## Tests and acceptance

- Test combined filters, empty states, add/validation and success/error messages, personal deletion confirmation, menu controls, hide/restore/restore-all, persistent preference and account isolation. Two-user tests: hide for A leaves B unaffected; cross-account/crafted requests fail; shared/default deletion still denied; shared detail/list/search honor preference; new default visible to both; FK cascade only removes preferences. Test migration and existing backend regression suite using isolated fixtures, not live user records.
- Verify rendered UI against both screenshots at desktop and phone widths if browser available; confirm no horizontal page overflow, contrast, keyboard navigation, focus, native dialogs/menus and toast behavior. Verify auth/one-time launch and existing extension API contract; run relevant extension compatibility tests without changing extension files. Mark unavailable real-browser or live checks NOT RUN.
- Exclude edit snippets, copy button, theme switch, syntax highlighting, favorites, imports/exports, performance tuning and unrelated features. No changes to extension source/package, Marketplace listing, identity or version 1.0.0.

## Authorized operations and stop

GitHub: create feature/ui-usability, implement, test, commit with the specified message, push and verify. Do not modify or merge main; no PR unless separately requested. Supabase: prepare and test the additive migration in isolation; do not apply to live Production yet. Vercel: no manual deployment/promotion/configuration changes; inspect actual branch deployment policy before push and report any automatic Preview; if push would automatically deploy Production, stop and report rather than proceeding without explicit release authorization. No destructive live operations. Stop after verified feature branch push and testing. Production migration/deployment will be a separate authorized release step; no extension rebuild/version increment/Marketplace upload.

## Completion report

Report baseline, branch and commit SHA, files changed, tests/results and screenshots or visual verification limitations, migration filename and tested schema/RLS behavior, GitHub push verification, Supabase live changes (none), Vercel actual deployment state, API compatibility and any remaining blockers/release prerequisites. Clearly distinguish implemented, tested, pushed and deployed.
