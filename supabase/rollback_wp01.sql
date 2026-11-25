BEGIN;

LOCK TABLE public.snippets IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT FROM public.snippets WHERE owner_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Preserve the ownership mapping and reconcile assigned snippets before rollback';
    END IF;
END
$$;

DROP POLICY snippets_select ON public.snippets;
DROP POLICY snippets_insert ON public.snippets;
DROP POLICY snippets_delete ON public.snippets;
REVOKE ALL ON public.snippets FROM snippet_app;
REVOKE ALL ON SEQUENCE public.snippets_sno_seq FROM snippet_app;
REVOKE USAGE ON SCHEMA public, snippet_private FROM snippet_app;
DROP TABLE snippet_private.web_sessions, snippet_private.revoked_vscode_sessions, snippet_private.auth_limits;
DROP SCHEMA snippet_private;
ALTER TABLE public.snippets DROP COLUMN owner_id;
DROP ROLE snippet_app;

-- Keep RLS enabled and direct Data API roles revoked. Do not restore the anonymous legacy app.
COMMIT;
