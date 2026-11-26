# WP-02 — Final authentication polish

**ID:** SNIPPO-WP02-FINAL-AUTH-POLISH
**Repository:** FunDood155/snippet_manager
**Verified baseline:** `feature/authentication` at `66c8a6e1ed2f7d93c6d2a6669bd2928ff393720c` (secure public registration).
**Implementation branch:** Continue `feature/authentication`; reconcile its current head before editing.
**Commit message:** `polish authentication experience`

## Objective

Complete three focused release improvements. Public registration, verification email delivery, verified web/VS Code login and snippet insertion have passed user testing; database showed one verified and one unverified account, zero legacy holds and four owned starter snippets. User elects to skip further password-recovery and privacy-policy work in this handoff; do not represent either as independently fully verified or assume an existing policy file. No unrelated redesign.

## 1. Account deletion request procedure

Currently `public.snippets.owner_id` references `auth.users(id) ON DELETE RESTRICT`; users with owned snippets cannot simply be deleted in the dashboard. Implement a small, discoverable support-based deletion procedure (not a new self-service destructive endpoint). Add a clear Account deletion / Request account deletion link on the authenticated website; provide concise accessible instructions using the existing support mailbox `snippo.support@gmail.com`, and document the procedure in the project and extension README as appropriate. No secrets, passwords, token hashes or snippet contents requested by email. Explain that permanent deletion includes the account and its owned snippets, requires verification of account ownership and explicit consent, and is not a mere sign-out; no unverified promises about completion times, backups or legal compliance.

Document an operator-only runbook: verify ownership securely and explicit deletion consent, resolve exact UUID, review scope/counts privately, prevent new writes for the target during cleanup (no firewall changes), revoke sessions/grants and ensure old credentials cannot use the application; remove only that UUID's owned snippets then delete that identity through supported Supabase Auth administration, handle dependent app records and verify no surviving owned rows or active sessions. Describe partial-failure handling and verification; keep unrelated accounts, unassigned legacy snippets and constraints intact. Do not recommend broad DELETE statements, exposing an admin/service-role key to clients, dropping constraints, or relying solely on token expiry. Verify current Auth/API behavior and existing schema before specifying operator steps. If safe operator deletion cannot be guaranteed with current controls, document the limitation rather than claiming automation exists. No actual account/data deletion or live database changes authorized.

## 2. Registration feedback

Inspect `auth.py` register/login/resend and `templates/auth.html`. Current 303 redirects to sign-in with a generic flash; tester did not notice instructions. Add a prominent accessible, durable-enough post-registration pending-verification state (dedicated confirmation screen or prominent login banner that survives normal redirect/navigation as appropriate). Clearly instruct checking inbox and Spam for a verification link, clicking Continue, then signing in; offer Resend confirmation and Sign in. Provide meaningful resend/cooldown feedback without revealing whether a particular email already exists or guaranteeing a message was sent. Preserve safe generic behavior for duplicate addresses, existing rate limits, CSRF, provider confirmation requirement, fixed email links and verified-identity checks. Do not enable auto-confirmation or log email secrets. Preserve the VS Code sign-in context when safe; if verification interrupts or expires an OAuth attempt, clearly instruct restarting sign-in from VS Code rather than silently losing context.

## 3. VS Code browser-to-editor handoff

Current `templates/vscode_callback.html` exposes manual Open VS Code / Manage my snippets / Open VS Code Insiders links; `auth.py` validates callback and renders query; `main.py` CSP does not permit callback scripts; extension `src/extension.ts` waits for URI with cancellation and five-minute expiry; `src/auth.ts` accepts only correct scheme/authority/path/state, single-use and PKCE exchange. After consent, attempt to open the correct fixed desktop callback automatically (prefer stable VS Code for default; keep Insiders manual fallback unless a safely validated scheme can be established). Use a small same-origin external script only on callback if needed, narrowly allow it in CSP, use server-validated fixed href/escaped values, no dynamic caller-supplied URL, inline script, external service, token logging or new token transport. Keep explicit Open VS Code and Open VS Code Insiders fallback buttons for browsers that block/require permission for custom protocols; never bypass OS/browser confirmation. Explain that opening the editor finishes sign-in; Manage my snippets must not falsely imply editor sign-in finished or silently strand the user. If handoff is blocked, make manual next step obvious; preserve callback access while offering website management (e.g. open management separately with safe rel). For declined consent, return to editor as cancellation, not success. Improve extension progress wording (waiting for browser / return to VS Code) and ensure cancel, timeout, sign-out, server change, denied callback, failed external launch and retries clean up correctly; no indefinite loading or false signed-in status. Preserve existing extension ID, command IDs, configuration, OAuth redirect, state/PKCE, token storage/refresh/revocation and owner isolation. Avoid polling/relay infrastructure; only change extension code as needed for the UX and cleanup.

## Acceptance / tests

- Visible account deletion instructions and support link; documented scoped procedure with no client admin privileges, no live deletion. Validate against schema and use isolated fixtures/mocks if testing deletion behavior.
- Registration and resend messaging visible, accessible and useful; indistinguishable public responses for duplicate/new addresses where needed; no email verification bypass, password/CSRF/rate-limit regressions. Verify ordinary web and VS Code-originated signup, verification, existing login and recovery regressions.
- Callback automatically attempts fixed VS Code protocol on successful consent where browser permits; blocked launch has usable manual fallback; stable and Insiders links valid; Manage my snippets remains usable; decline/cancel/timeout/retry clear progress; wrong state/scheme/replay do not authenticate. No promise that browser permissions can be bypassed. Verify manual hosted browser/desktop flow after later authorized deployment.
- Run existing backend and extension test suites, add focused regression tests, compile extension and package local VSIX if feasible for testing. Report actual commands/results, including any browser/manual checks not run. Keep package version/IDs unchanged; final release build later.

## Scope and operations

Authorize implementation, ordinary in-scope tests, commit/push on `feature/authentication` only when activated in Work chat. No merge to main, production/preview deploy, Supabase write/migration, SMTP/config/firewall change, account deletion, policy creation, paid services, Marketplace publication or unrelated changes. Preserve current data and security controls. If a real prerequisite outside scope is discovered, report it. Handoff publication is not execution.

## Report back

Branch and commit SHA, files changed, three fixes and design decisions, exact tests/build results and limitations, GitHub actions, explicit confirmation of no live Supabase/Vercel changes or release, and short manual retest checklist. 
