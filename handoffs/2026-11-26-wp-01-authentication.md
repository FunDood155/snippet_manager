# Snippet Manager — WP-01: Authentication and user isolation

Status: Ready for Work (requires explicit activation)
Repository: FunDood155/snippet_manager
Reviewed baseline: main @ 3fbffd13a16e9b577b9e4d2668854a94f40bf5a7
Handoff branch: features/handoffs (documentation only)
Implementation branch: feature/authentication (create from latest main; read main only)
Commit message: implement authentication

## 1. Objective
Give the Flask website and VS Code extension one account and a private, cloud-synchronized snippet library. Preserve existing snippet operations and data. Make this the prerequisite for easier installation and future extension distribution. Keep the current Flask/Jinja2, PostgreSQL/Supabase and TypeScript stack; keep UI basic until redesign.

## 2. Scope
- Inspect latest source, actual schema and deployment configuration read-only; reconcile baseline drift. Review main.py, templates/index.html, requirements.txt, migrate.py, vscode_extension/src/extension.ts and package.json. Do not run the legacy migration script.
- Evaluate Supabase Auth as the preferred managed identity solution against its current docs, email delivery/confirmation limits, free-tier constraints, and desktop sign-in compatibility. Document the chosen approach. Do not implement a custom password/token protocol if an established supported flow suffices.
- Implement registration, login, logout, session persistence, clear validation/errors and email confirmation/recovery flow where required by the chosen provider. Provide basic accessible forms. Protect cookie sessions with secure attributes, CSRF protection, rotation/revocation appropriate to the chosen model, and abuse protections for authentication endpoints. Never store plaintext passwords.
- Implement VS Code sign-in/sign-out and signed-in status using browser-based authorization. Use an established secure flow with short-lived single-use authorization, state and PKCE where applicable, validated redirect targets, secure token exchange/refresh, expiry and revocation. Handle cancellation, expired credentials, connection errors and restart; use VS Code SecretStorage, never plaintext settings or logs. No privileged database keys in clients. Keep three existing commands working for signed-in users; handle unauthenticated users with a clear sign-in prompt.
- Enforce server-side authentication and owner predicates for every snippet read/search/create/delete and web/API route, including categories and individual IDs. Use trusted identity, not client-supplied ownership. Preserve API response compatibility where safe; define authentication errors clearly. Reject cross-account access and anonymous writes/reads. Parameterize SQL.
- Prepare versioned, reviewed migration files to add ownership, foreign keys/indexes as justified, RLS and least-privilege grants. Ensure privileged server connections cannot bypass application ownership checks. Preserve all existing records; quarantine unassigned legacy snippets from normal users. No automatic assignment to first registrant. Include a safe explicit owner-mapping/backfill plan, backup/rollback procedure and verification of record counts; actual ownership assignment requires confirmed intended account.
- Add focused backend and extension tests, environment variable names/placeholders, setup/test instructions, and a reproducible local VSIX build. Do not publish a package or distribute a public release.

## 3. Acceptance criteria
- Registration/login/logout succeed with valid inputs; invalid, duplicate or unconfirmed accounts handled safely without leaking credentials; sessions/tokens expire and can be revoked according to documented semantics.
- VS Code browser login, callback validation, restart persistence, logout, token renewal, invalid/expired/replayed authorization, and canceled login behave safely.
- Two synthetic users can independently create/list/search/read/delete their own snippets on web and API; cross-user IDs, category queries, forged ownership, anonymous requests and direct database API access fail appropriately. Verify RLS for the intended roles with test fixtures, not real user data.
- Existing snippet names, categories, code and IDs are preserved by migration. No legacy data becomes publicly accessible; no destructive migration.
- Existing extension show/search/insert work with authenticated synthetic data. Compilation, tests and packaging pass or blockers are explicitly reported. No secrets in git, logs, packages or report.
- Use isolated test database/auth environment or mocks where live test resources are unavailable. Record which checks are live versus mocked. Do not claim real sign-in or RLS verification if untested.

## 4. Security and compatibility
Use current official documentation. Minimize dependencies, maintain free-tier compatibility, and keep existing behavior except required authentication changes. Inspect dependency findings and distinguish build-only from distributed risks; fix narrowly if necessary for this task. No public/shared cache of private responses. Design identity and API contracts so later account-scoped local caching can be added safely. No caching implementation, performance rewrite, snippet editing, broad UI redesign, Marketplace publishing, or portfolio cleanup in this package. Avoid real snippets or private infrastructure details in public commits or reports.

## 5. Authorized operations and stop condition
After user activation only:
- GitHub: create feature/authentication from latest main; implement, test, commit and push solely to feature/authentication. Read main only. Never commit, push, merge, open a PR targeting main, change main or merge the handoff branch. Do not write to features/handoffs. Do not change visibility, settings or history.
- Supabase: inspect the correct Snippet Manager project read-only. Prepare migrations and test against isolated/local fixtures. No live schema/data/auth/config changes or real owner assignment in this authorization. Report exact proposed live migration and configuration steps for separately authorized integration.
- Vercel: inspect only if accessible; no intentional Preview or Production deploy, promotion, or settings change. Check whether branch pushes automatically deploy; if they could affect live data or expose insecure code, stop before pushing and report. Deployment configuration was not verified in Planning; do not assume it.
- No TARVX changes. No destructive operations, credentials rotation, public release or Marketplace actions. Stop after verified implementation branch push (or report the blocker and stop safely). Never modify main, even to resolve a blocker. Do not begin the next phase.

## 6. Tests
Run backend unit/integration tests covering registration, session/token security, all route authorization, CSRF, isolation and error paths. Exercise migration and RLS on isolated PostgreSQL/Supabase fixtures; test preservation, idempotency where applicable and rollback. Test extension auth flow and existing commands using mocked or isolated endpoints; run npm ci, compile, relevant tests, and package. Where practical, test a clean VS Code install with synthetic data. Record commands, results and skipped cases; do not run live mutation tests. Verify branch diff and unchanged main.

## 7. Report back
Report base and final branch/commit, files changed, actual tests and results, auth architecture and configuration requirements, migration/backfill/rollback plan, known limitations, dependency findings, GitHub actions, Supabase and Vercel effects, and whether stop condition was met. Include a manual test checklist and any separately authorized integration steps needed. Explicitly distinguish implemented/tested/pushed from live-verified/deployed. Do not claim Marketplace readiness or publish the extension until live authentication/isolation and release gates are independently verified.
