BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '20s';

-- Deployment tooling can inject the privately reviewed JSON fingerprints here.
-- wp04_review
LOCK TABLE auth.users IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.snippets IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.default_snippets IN SHARE MODE;

-- Keep before-images private and together with the deletion transaction.
CREATE TABLE snippet_private.wp04_snippet_archive (
    sno integer PRIMARY KEY,
    original_row jsonb NOT NULL
);
REVOKE ALL ON snippet_private.wp04_snippet_archive
    FROM PUBLIC, anon, authenticated, service_role, snippet_app, snippet_starter;
ALTER TABLE snippet_private.wp04_snippet_archive ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    legacy_ids CONSTANT integer[] := ARRAY[1, 2, 3, 9, 10, 11, 14, 15, 16];
    seeded_ids CONSTANT integer[] := ARRAY[43, 44, 45, 46, 47, 48, 49, 50, 52, 53, 54, 55];
    reviewed jsonb := nullif(current_setting('snippet.wp04_review', true), '')::jsonb;
    actual jsonb;
    removed integer;
BEGIN
    -- Fresh installs skip data cleanup. Any populated candidate set requires review.
    SELECT jsonb_object_agg(s.sno, encode(sha256(convert_to(to_jsonb(s)::text, 'UTF8')), 'hex'))
      INTO actual FROM public.snippets s WHERE sno = ANY (legacy_ids || seeded_ids);
    IF actual IS NULL AND reviewed IS NULL THEN
        RETURN;
    END IF;

    IF reviewed IS NULL OR actual IS DISTINCT FROM (reviewed -> 'candidates')
        OR (SELECT count(*) FROM jsonb_object_keys(actual)) <> 21
        OR (SELECT encode(sha256(convert_to(to_jsonb(s)::text, 'UTF8')), 'hex')
              FROM public.snippets s WHERE s.sno = 51 AND s.owner_id IS NOT NULL)
            IS DISTINCT FROM (reviewed ->> 'protected')
        OR (reviewed ->> 'protected') IS NULL
        OR EXISTS (SELECT 1 FROM public.snippets WHERE sno = ANY (legacy_ids) AND owner_id IS NOT NULL)
        OR (SELECT count(*) FROM public.default_snippets) <> 4
        OR (SELECT count(*) FROM (
                SELECT s.owner_id
                FROM public.snippets s
                JOIN public.default_snippets d USING (name, cat, code)
                WHERE s.sno = ANY (seeded_ids) AND s.owner_id IS NOT NULL
                GROUP BY s.owner_id
                HAVING count(*) = 4 AND count(DISTINCT d.sno) = 4
            ) verified_owners) <> 3
    THEN
        RAISE EXCEPTION 'WP-04 rows differ from the approved cleanup scope';
    END IF;

    INSERT INTO snippet_private.wp04_snippet_archive (sno, original_row)
    SELECT s.sno, to_jsonb(s) FROM public.snippets s WHERE sno = ANY (legacy_ids || seeded_ids);

    DELETE FROM public.snippets s
    USING snippet_private.wp04_snippet_archive a
    WHERE s.sno = a.sno AND to_jsonb(s) = a.original_row;
    GET DIAGNOSTICS removed = ROW_COUNT;
    IF removed <> 21 THEN
        RAISE EXCEPTION 'WP-04 expected to delete exactly 21 reviewed rows';
    END IF;
END $$;

-- Supabase owns auth.users. Leave the trigger binding in place and retire its
-- body and write permissions without requiring managed-table owner privileges.
CREATE OR REPLACE FUNCTION snippet_private.provision_starter_snippets()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    RETURN NEW;
END
$$;
DROP POLICY snippets_insert_starters ON public.snippets;
REVOKE INSERT (owner_id, name, cat, code) ON public.snippets FROM snippet_starter;
REVOKE USAGE ON SEQUENCE public.snippets_sno_seq FROM snippet_starter;
REVOKE SELECT (user_id), INSERT (user_id) ON snippet_private.pending_starter_accounts FROM snippet_starter;
REVOKE DELETE ON snippet_private.pending_starter_accounts FROM snippet_starter;

COMMIT;
