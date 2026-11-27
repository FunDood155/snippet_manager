BEGIN;

CREATE TABLE snippet_private.hidden_default_snippets (
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    snippet_id integer REFERENCES public.default_snippets(sno) ON DELETE CASCADE,
    PRIMARY KEY (user_id, snippet_id)
);

CREATE INDEX hidden_default_snippets_snippet_idx ON snippet_private.hidden_default_snippets (snippet_id);

REVOKE ALL ON snippet_private.hidden_default_snippets
    FROM PUBLIC, anon, authenticated, service_role, snippet_app, snippet_starter;
GRANT SELECT, INSERT, DELETE ON snippet_private.hidden_default_snippets TO snippet_app;
ALTER TABLE snippet_private.hidden_default_snippets ENABLE ROW LEVEL SECURITY;
ALTER TABLE snippet_private.hidden_default_snippets FORCE ROW LEVEL SECURITY;
CREATE POLICY hidden_default_snippets_select ON snippet_private.hidden_default_snippets FOR SELECT TO snippet_app
    USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY hidden_default_snippets_insert ON snippet_private.hidden_default_snippets FOR INSERT TO snippet_app
    WITH CHECK (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY hidden_default_snippets_delete ON snippet_private.hidden_default_snippets FOR DELETE TO snippet_app
    USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);

COMMIT;
