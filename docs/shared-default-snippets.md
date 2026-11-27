# Shared default snippets

The four starter templates live in `public.default_snippets`. Verified users see these alongside just their own personal snippets. The existing website and API search the combined library, and shared IDs work with the existing read endpoint. The app role can only select defaults, and only with a verified owner context set by Flask. Supabase API roles have no access. Users can create a personal snippet with the same name as a default.

## Managing defaults

In the Supabase Table Editor, an authorized database operator can add or edit a row in `public.default_snippets` by setting `name`, `cat` and `code`. Leave `sno` unset when inserting so the database assigns it. IDs from 2,000,000,000 to 2,147,483,647 are reserved for defaults. The personal table constraint and sequence cap enforce separation without changing existing IDs or resetting the sequence. An edit to a shared row appears for all users. Keep private code out of this table.

## Rollout

1. Apply `20261127193609_shared_default_snippets.sql` as the project database operator. Confirm four defaults, the ID bounds, and the runtime grants. The old backend can continue reading the existing personal copies.
2. Deploy the new Flask backend. Verify the exact deployment serves the permanent URL and that an existing authorized account can read shared and personal rows. During this stage old seeded copies can still appear. Check that the existing VS Code client sees the same library and maintains account isolation.
3. Reinspect the approved IDs privately. The legacy scope is only 1, 2, 3, 9, 10, 11, 14, 15 and 16 with no owner. The seed scope is only 43–50 and 52–55, with three complete owner groups matching the original name, category and code tuples. Verify the live provisioning function against the original migration. Record SHA-256 fingerprints and confirm the protected row 51 and its owner. Scope does not include new accounts, additional exact matches, or altered copies.
4. Run `20261127193616_retire_starter_copies.sql` transactionally. On the approved legacy database the operator injects a transaction-local `set_config('snippet.wp04_review', review_json, true)` statement at the comment `-- wp04_review` in the migration. The JSON contains `candidates`, an object mapping each reviewed ID to the lowercase hex SHA-256 of `convert_to(to_jsonb(s)::text, 'UTF8')` for the full personal-table row `s`, and `protected`, the corresponding hash for row 51. Keep this manifest out of Git and public logs. An empty fresh database needs no review input. If any approved row differs or a lock times out, the transaction aborts.
5. Confirm exactly 21 archived and removed rows when running the approved legacy cleanup, four shared rows, unchanged accounts and personal rows, and no new provisioning. The managed Auth table owner is separate from the migration role. The migration retains the trigger binding with an inert invoker function and removes the starter role's writes and policy. Existing pending tracker rows, if any, remain private and inert. Record the hosted migration history versions alongside the source filenames because the connector may assign different timestamps.

## Recovery

The cleanup transaction records the full before-images in `snippet_private.wp04_snippet_archive`. It is outside the exposed schema, with RLS enabled and no app or Data API grants. Restrict access to database operators and retain it only as needed for rollback and applicable account deletion requests.

Prefer fixing forward. The deployed backend depends on `public.default_snippets`. Before rolling back to old provisioning, validate the archive against the reviewed IDs and fingerprints and confirm that original non-null owners still exist and IDs are free. Under the same lock ordering, restore only reviewed rows from the archive with `jsonb_populate_record(NULL::public.snippets, original_row)` and explicit column mapping. Do not use conflict handling to overwrite or silently skip data. Leave both sequences intact and verify the personal sequence is ahead of restored IDs. Rehearse restoring the original function, policy and scoped grants from the starter migration without replaying its role or table creation statements. Enable old provisioning only in a coordinated rollback after validating the restored data and old backend. Keep the shared table until the deployed backend no longer reads it.

## Per-account visibility and web dashboard

The web library offers **Hide default** on shared cards and **Hidden defaults**
for individual restore and restore-all. A hidden default disappears from that
account's list, search, and detail responses, including in VS Code. Preferences
follow the account across devices and never modify a shared row. New shared
defaults are visible until an account chooses to hide them.

Before deploying this backend, apply
`supabase/migrations/20261127201346_hidden_default_snippets.sql` to the target
database. It adds an initially empty, private preference table with forced
owner-scoped RLS and SELECT, INSERT, and DELETE grants for `snippet_app`.
Both foreign keys cascade into preferences only. Verify the migration in an
isolated database before any Production cutover. A Preview requires a
compatible migrated test database for authenticated library pages.

The previous backend can run with the preference table in place. During that
rollback, hidden defaults become visible until the new backend is redeployed.
Keep the table and its rows so preferences survive rollback. Do not drop the
table while any deployed backend still reads it.
