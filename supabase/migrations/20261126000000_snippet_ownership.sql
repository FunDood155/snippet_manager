BEGIN;

-- Provision the login's password separately. Never store it in a migration.
CREATE ROLE snippet_app NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE SCHEMA snippet_private;
REVOKE ALL ON SCHEMA snippet_private FROM PUBLIC;
GRANT USAGE ON SCHEMA public, snippet_private TO snippet_app;

ALTER TABLE public.snippets
    ADD COLUMN owner_id uuid REFERENCES auth.users (id) ON DELETE RESTRICT;

CREATE INDEX snippets_owner_name_idx ON public.snippets (owner_id, name);
CREATE INDEX snippets_owner_cat_idx ON public.snippets (owner_id, cat);

REVOKE ALL ON public.snippets FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SEQUENCE public.snippets_sno_seq FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, DELETE ON public.snippets TO snippet_app;
GRANT INSERT (owner_id, name, cat, code) ON public.snippets TO snippet_app;
GRANT USAGE ON SEQUENCE public.snippets_sno_seq TO snippet_app;

ALTER TABLE public.snippets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.snippets FORCE ROW LEVEL SECURITY;
CREATE POLICY snippets_select ON public.snippets FOR SELECT TO snippet_app
    USING (owner_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY snippets_insert ON public.snippets FOR INSERT TO snippet_app
    WITH CHECK (owner_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY snippets_delete ON public.snippets FOR DELETE TO snippet_app
    USING (owner_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);

CREATE TABLE snippet_private.web_sessions (
    handle_hash text PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    access_token text NOT NULL,
    refresh_token text NOT NULL,
    token_expires_at bigint NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE INDEX web_sessions_user_idx ON snippet_private.web_sessions (user_id);
CREATE INDEX web_sessions_expiry_idx ON snippet_private.web_sessions (expires_at);

CREATE TABLE snippet_private.revoked_vscode_sessions (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE
);
CREATE INDEX revoked_vscode_sessions_user_idx ON snippet_private.revoked_vscode_sessions (user_id);

CREATE TABLE snippet_private.auth_limits (
    bucket text PRIMARY KEY,
    window_id bigint NOT NULL,
    hits integer NOT NULL
);
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA snippet_private TO snippet_app;

COMMIT;
