BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '20s';

ALTER TABLE public.snippets ADD COLUMN language text CHECK (language IN ('python', 'javascript', 'typescript', 'html', 'css', 'sql', 'json', 'shellscript', 'plaintext')),
    ADD COLUMN template boolean NOT NULL DEFAULT false;
ALTER TABLE public.default_snippets ADD COLUMN language text CHECK (language IN ('python', 'javascript', 'typescript', 'html', 'css', 'sql', 'json', 'shellscript', 'plaintext'));
GRANT INSERT (language, template), UPDATE (language, template) ON public.snippets TO snippet_app;

CREATE TABLE snippet_private.recent_personal_snippets (
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    snippet_id integer,
    used_at timestamptz NOT NULL,
    PRIMARY KEY (user_id, snippet_id),
    FOREIGN KEY (user_id, snippet_id) REFERENCES public.snippets(owner_id, sno) ON DELETE CASCADE
);
CREATE INDEX recent_personal_snippets_user_time_idx ON snippet_private.recent_personal_snippets (user_id, used_at DESC, snippet_id DESC);

REVOKE ALL ON snippet_private.recent_personal_snippets FROM PUBLIC, anon, authenticated, service_role, snippet_app, snippet_starter;
GRANT SELECT (user_id, snippet_id, used_at), INSERT (user_id, snippet_id, used_at),
      UPDATE (used_at), DELETE ON snippet_private.recent_personal_snippets TO snippet_app;
ALTER TABLE snippet_private.recent_personal_snippets ENABLE ROW LEVEL SECURITY;
ALTER TABLE snippet_private.recent_personal_snippets FORCE ROW LEVEL SECURITY;
CREATE POLICY recent_personal_select ON snippet_private.recent_personal_snippets FOR SELECT TO snippet_app USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY recent_personal_insert ON snippet_private.recent_personal_snippets FOR INSERT TO snippet_app WITH CHECK (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY recent_personal_update ON snippet_private.recent_personal_snippets FOR UPDATE TO snippet_app
    USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid) WITH CHECK (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY recent_personal_delete ON snippet_private.recent_personal_snippets FOR DELETE TO snippet_app USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);

CREATE TABLE snippet_private.recent_default_snippets (
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    snippet_id integer,
    used_at timestamptz NOT NULL,
    PRIMARY KEY (user_id, snippet_id),
    FOREIGN KEY (snippet_id) REFERENCES public.default_snippets(sno) ON DELETE CASCADE
);
CREATE INDEX recent_default_snippets_user_time_idx ON snippet_private.recent_default_snippets (user_id, used_at DESC, snippet_id DESC);

CREATE INDEX recent_default_snippets_target_idx ON snippet_private.recent_default_snippets (snippet_id);

REVOKE ALL ON snippet_private.recent_default_snippets FROM PUBLIC, anon, authenticated, service_role, snippet_app, snippet_starter;
GRANT SELECT (user_id, snippet_id, used_at), INSERT (user_id, snippet_id, used_at),
      UPDATE (used_at), DELETE ON snippet_private.recent_default_snippets TO snippet_app;
ALTER TABLE snippet_private.recent_default_snippets ENABLE ROW LEVEL SECURITY;
ALTER TABLE snippet_private.recent_default_snippets FORCE ROW LEVEL SECURITY;
CREATE POLICY recent_default_select ON snippet_private.recent_default_snippets FOR SELECT TO snippet_app USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY recent_default_insert ON snippet_private.recent_default_snippets FOR INSERT TO snippet_app WITH CHECK (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid AND NOT EXISTS (
        SELECT 1 FROM snippet_private.hidden_default_snippets h
        WHERE h.user_id = recent_default_snippets.user_id AND h.snippet_id = recent_default_snippets.snippet_id
    ));
CREATE POLICY recent_default_update ON snippet_private.recent_default_snippets FOR UPDATE TO snippet_app
    USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid) WITH CHECK (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid AND NOT EXISTS (
        SELECT 1 FROM snippet_private.hidden_default_snippets h
        WHERE h.user_id = recent_default_snippets.user_id AND h.snippet_id = recent_default_snippets.snippet_id
    ));
CREATE POLICY recent_default_delete ON snippet_private.recent_default_snippets FOR DELETE TO snippet_app USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);

COMMIT;
