-- Block site/API access and pause provider signup before rollback.
-- Archive hold IDs and cutoffs privately for a future forward rollout.
BEGIN;
TRUNCATE snippet_private.web_sessions;
DROP TABLE snippet_private.email_flows, snippet_private.session_cutoffs, snippet_private.legacy_email_holds;
COMMIT;
