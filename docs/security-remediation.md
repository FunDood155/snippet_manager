# Security remediation rollout

WP-14 prepares the security candidate. The owner authorizes platform changes,
database application and Production release separately.

## CI and main protection

In GitHub **Settings → Rules → Rulesets**, target `main` and require PRs.
Choose **Backend and database** and **Callback and VS Code** from the
**Security checks** workflow as required GitHub Actions checks after a verified
run. Require one approval if an independent reviewer is available. A solo
owner can still require PRs and checks with zero mandatory approvals, then
increase the approval rule when there is a second maintainer. Restrict force
push and deletion, review integration permissions and record who can recover
the repository. Test the policy on a reviewed PR before enforcing it. Keep
any break-glass access restricted to a named owner and audit its use. Verify
Vercel's Git integration releases the reviewed `main` SHA.

Run the staged-file guard with `python scripts/check_tracked_files.py`.
It flags runtime filenames, SQLite content and common credential formats. It
only prints paths. Keep allowlists narrow and limited to deliberate public
fixtures. The guard does not scan historical commits or replace secret
scanning. Classify the four historical SQLite snapshots and one JSON snapshot
from WP-13 privately. If sensitive content is confirmed, use the owner
incident process and obtain separate authorization for rotation or history
changes. Public forks and caches can retain earlier content.

## Database, Preview and recovery

1. Verify isolated Preview Auth and PostgreSQL are the same test project,
   confirm they differ from Production, validate protected Preview URLs, and
   provision the `snippet_app` runtime login. Use `SNIPPET_DATABASE_URL` and a
   distinct session key. The candidate rejects dynamic Vercel Preview traffic
   unless `SNIPPET_ISOLATED_PREVIEW=1`. Set it in Preview only after isolation,
   schema application and deployment access protection are verified. A 503
   before that opt-in is expected. CI never needs these credentials.
2. Verify the nine predecessor migration names and storage/restore evidence.
   Apply only `20261129020000_security_remediation.sql` when authorized.
   The applying role must read the documented Supabase Auth metadata to own
   the two private, fixed-search-path functions. Runtime has no direct Auth
   schema access. Check owner and routine grants, two-user isolation and
   picker behavior. Plan index creation around activity on large libraries.
3. The migration adds private state, routines and indexes without editing
   existing rows. The old backend can use the expanded schema, but it does
   not honor the new transition state. Avoid a mixed-version traffic window
   while authentication mutations are available. Roll forward if possible.
   If an older binary must serve traffic after candidate activity, close
   affected routes until pending recovery and OAuth invalidations are
   reconciled. Keep the additive schema, individual tombstones and cutoff
   state. Do not drop them as a deployment rollback.
4. Grant revocation retains local session tombstones. A provider timeout or
   database failure leaves the local transition pending. Retry revoke-all
   from the signed-in website, or use a verified recovery link and a
   different password after an uncertain password update. Retry VS Code
   sign-in after any outstanding authorization-code expiry. Requests that
   passed the auth check before the barrier was committed may finish.
5. Verify project consumers and rollback versions use only
   `SNIPPET_DATABASE_URL`. The historical importer is disabled. Once owner
   review is complete, remove the unused `DATABASE_URL` entry separately
   under **Vercel → Project Settings → Environment Variables** for Preview
   and Production. Review the underlying login and active consumers before
   revoking a credential. Never copy environment values into tickets or CI.

Anonymous forms keep shared and per-subject five-minute ceilings, with keyed
subjects and per-subject rejection ahead of shared admission. The hard shared
ceiling can still be exhausted by many independent identities. For hosted
Auth, verify the confirmation setting, SMTP quotas and Supabase rate limits
through project settings. The leaked-password setting is Pro and above.
On Free, review a longer minimum and use verified email and password
managers. No plan upgrade or mail setting change is part of WP-14.
[Supabase password security](https://supabase.com/docs/guides/auth/password-security)
[Supabase OAuth revokeGrant](https://supabase.com/docs/reference/javascript/oauth-server-revokegrant)

## Library and extension compatibility

The library permits up to 1,000 personal snippets and 16 MiB of personal
name, category and code text per account, measured as UTF-8 before JSON
encoding. Writes that exceed a quota are rejected. Existing over-budget
libraries can shrink entries or delete items. Browser paging stays at 40
cards. Individual authorized reads and deletes remain available. API
duplicate names still return 409, and quota errors return 422.

The snippet list allows 300 requests per account in a five-minute window.
Search and API category filters are limited to 256 characters. Legacy v1 and
v2 still return arrays in ID order, up to 1,000 items and about 3 MiB of
serialized JSON. An over-budget list returns 413 with recovery guidance and
no partial array. A caller can opt into keyset pagination with `?limit=40`
and follow `X-Snippo-Next-After` by passing it as `after` with the same
filters. Pages are capped at 40 records and the same byte ceiling. Concurrent
inserts and deletes are visible on later pages. If an individual historical
record exceeds this list budget, use the web library or its individual API
endpoint. The VS Code picker preserves single-request search and shows a
safe recovery message if its list is too broad.

The desktop extension validates and limits JSON before rendering. It
compares the exact stored token version before clearing an earlier session.
VS Code SecretStorage does not expose an atomic cross-host compare-and-delete.
Verify in native desktop testing before public release.

## Data retention and future ACLs

The operator archive is private and contains migration before-images for
historical rollback investigation. The project owner should document the
purpose, approve a review and retention date after testing recovery, and
record archive/backup handling in account deletion. Never copy archive
contents into logs, support tickets or public Git history. See
[Account deletion](account-deletion.md). No purge is approved here.

The app prunes expired credential rows opportunistically in bounded batches.
Backup retention needs its own verified schedule. Runtime and its backups
remain trusted with valid bearer material. OAuth denial records are retained
because their safe expiry cannot be inferred from a current access JWT alone.
New SQL migrations should explicitly revoke default API-role privileges and
apply forced owner RLS to tenant data. Keep credential tables private and
test effective grants with an ordinary runtime login. Review any broader
managed default-privilege changes as a separate platform operation.
