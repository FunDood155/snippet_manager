# WP-15 — Dependency and code health
**ID:** SNIPPO-WP15-DEPENDENCY-HEALTH
**Branch:** create feature/dependency-health from verified WP-14 commit 6e87020203233374e5739695704599427cdd2f84 (feature/security-remediation), NOT main or handoff branch.
**Commit:** improve dependency and code health
**Goal:** address SEC-012 and SEC-013 from WP-13 with minimum necessary changes, preserve WP-14 security fixes. This is focused maintenance plus a short report, not another comprehensive audit. Use priority order below; stop safely with a partial report if usage is limited.

## P0 — Dependency security (first)
- On candidate, inspect current requirements, npm manifest/lock and installed resolves. In isolated environment run current full and runtime-only npm audit and pip-audit or equivalent; compare with WP-13's 22 unique build/development advisories in @azure/msal-node, brace-expansion, fast-uri, glob, markdown-it, minimatch, qs, undici. Do not assume old advisory versions still apply. WP-13 reported zero runtime npm and zero local Python advisories.
- Fix verified high/moderate advisory paths via smallest compatible upgrades or narrowly justified overrides, especially vsce/build tooling. Avoid forced audit fixes, broad upgrades or changes to VS Code engine/host. Preserve package identity and functionality. Verify clean install, lock integrity, compile/lint/tests and package. Re-scan; report residual advisory IDs, severity, dependency path, actual exposure and blocker if no compatible fix. No lowering security to silence scans.

## P1 — Reproducibility (SEC-013)
- Pin/lock Python runtime dependencies including transitives using compatible versions verified in the actual supported Python/Vercel target; prefer simple deployable requirements or lock consumed by CI and Vercel, with hashes where supported. Validate clean resolve, pip check, vulnerability scan and backend suite. Record runtime assumptions; do not claim hosted dependency resolution if Preview cannot establish it.
- Preserve existing two GitHub Actions required-check job names. Add lightweight dependency audit checks in existing workflow if practical; distinguish advisory findings from network/scanner failures. No deployment secrets, paid services, or privileged CI.

## P2 — Minimal code health
- Remove only demonstrably unused direct packages/imports or redundant dead code with evidence and regression coverage. Check deprecations directly affected by updates; make only necessary compatibility fixes. No stylistic refactors, architecture changes, speculative cleanup or re-auditing all files. Keep security limits, auth, migration, templates, preferences, UI and performance intact. Skip optional cleanup if time/usage limited.

## Verification and release
- Run existing isolated PostgreSQL/Python tests (WP-14 baseline 70), callback JS (3), extension tests (19), compile/lint, dependency scans and clean build. Focus on affected paths; full browser/performance/security regression belongs to WP-16. No production fixtures. Report actual counts and failures. Repackage unpublished extension 1.1.2 from cumulative candidate, keep same version if still unpublished, verify contents/identity/hash; deliver candidate VSIX. If version already published, report collision before release decisions.
- Commit/push only tested scoped changes to feature/dependency-health; verify exact parent/diff/SHA, CI and automatic Preview if available. Preserve WP-14 Preview isolation gate. Do not enable it or claim runtime validation merely because deployment is READY. If no necessary changes, report and retain verified predecessor without empty commit.
- No live Supabase changes or migration application, Vercel/GitHub configuration changes, main merge, Production promotion, Marketplace publication, history rewrite, new features, paid services. Keep WP-14 pending migration, hosted provider tests, branch protection, credential removal, archive/history/backup owner actions explicitly outstanding for WP-16/17. No WP-14 rework unless a dependency compatibility issue requires it; report blocker instead of expanding scope.

## Short deliverable
Produce Snippo-WP15-Dependency-Health.md (Library if available), preferably concise: P0/P1/P2 status; before/after dependency versions and advisory counts; unresolved IDs/reasons; files/commit/parent; test and CI results; VSIX version/hash; Preview and unchanged Production; exact WP-16 predecessor and carryover gates. Preserve partial findings if interrupted, no untested push or claims of completion. Stop before WP-16.
