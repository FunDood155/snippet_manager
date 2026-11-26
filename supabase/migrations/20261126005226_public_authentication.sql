BEGIN;

-- Snapshot all pre-cutover identities. Run only with registration paused.
CREATE TABLE snippet_private.legacy_email_holds (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE
);
INSERT INTO snippet_private.legacy_email_holds (user_id)
SELECT id FROM auth.users;
GRANT SELECT ON snippet_private.legacy_email_holds TO snippet_app;

CREATE TABLE snippet_private.session_cutoffs (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    invalid_through bigint NOT NULL
);
GRANT SELECT, INSERT, UPDATE ON snippet_private.session_cutoffs TO snippet_app;

CREATE TABLE snippet_private.email_flows (
    handle_hash text PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    access_token text NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE INDEX email_flows_expiry_idx ON snippet_private.email_flows (expires_at);
GRANT SELECT, INSERT, DELETE ON snippet_private.email_flows TO snippet_app;
-- PostgreSQL requires a column UPDATE grant for SELECT FOR UPDATE.
GRANT UPDATE (expires_at) ON snippet_private.email_flows TO snippet_app;

COMMIT;
