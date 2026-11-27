BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '20s';

GRANT UPDATE (name, cat, code) ON public.snippets TO snippet_app;
CREATE POLICY snippets_update_owned ON public.snippets FOR UPDATE TO snippet_app
    USING (owner_id = nullif(current_setting('snippet.owner_id', true), '')::uuid)
    WITH CHECK (owner_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);

ALTER TABLE public.snippets ADD CONSTRAINT snippets_owner_sno_key UNIQUE (owner_id, sno);

CREATE TABLE snippet_private.favorite_personal_snippets (
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    snippet_id integer,
    PRIMARY KEY (user_id, snippet_id),
    FOREIGN KEY (user_id, snippet_id) REFERENCES public.snippets(owner_id, sno) ON DELETE CASCADE
);

CREATE TABLE snippet_private.favorite_default_snippets (
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    snippet_id integer REFERENCES public.default_snippets(sno) ON DELETE CASCADE,
    PRIMARY KEY (user_id, snippet_id)
);

CREATE INDEX favorite_default_snippets_snippet_idx
    ON snippet_private.favorite_default_snippets (snippet_id);

REVOKE ALL ON snippet_private.favorite_personal_snippets, snippet_private.favorite_default_snippets
    FROM PUBLIC, anon, authenticated, service_role, snippet_app, snippet_starter;
GRANT SELECT, INSERT, DELETE ON snippet_private.favorite_personal_snippets, snippet_private.favorite_default_snippets
    TO snippet_app;

ALTER TABLE snippet_private.favorite_personal_snippets ENABLE ROW LEVEL SECURITY;
ALTER TABLE snippet_private.favorite_personal_snippets FORCE ROW LEVEL SECURITY;
CREATE POLICY favorite_personal_select ON snippet_private.favorite_personal_snippets FOR SELECT TO snippet_app
    USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY favorite_personal_insert ON snippet_private.favorite_personal_snippets FOR INSERT TO snippet_app
    WITH CHECK (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY favorite_personal_delete ON snippet_private.favorite_personal_snippets FOR DELETE TO snippet_app
    USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);

ALTER TABLE snippet_private.favorite_default_snippets ENABLE ROW LEVEL SECURITY;
ALTER TABLE snippet_private.favorite_default_snippets FORCE ROW LEVEL SECURITY;
CREATE POLICY favorite_default_select ON snippet_private.favorite_default_snippets FOR SELECT TO snippet_app
    USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY favorite_default_insert ON snippet_private.favorite_default_snippets FOR INSERT TO snippet_app
    WITH CHECK (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);
CREATE POLICY favorite_default_delete ON snippet_private.favorite_default_snippets FOR DELETE TO snippet_app
    USING (user_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);

COMMIT;
