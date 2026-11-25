BEGIN;

-- Remove the function and its dependent trigger without needing ownership of auth.users.
GRANT snippet_starter TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;
DROP FUNCTION snippet_private.provision_starter_snippets() CASCADE;
DROP POLICY snippets_insert_starters ON public.snippets;
REVOKE ALL ON public.snippets FROM snippet_starter;
REVOKE ALL ON SEQUENCE public.snippets_sno_seq FROM snippet_starter;
REVOKE USAGE ON SCHEMA public, snippet_private FROM snippet_starter;
DROP TABLE snippet_private.pending_starter_accounts;
DROP ROLE snippet_starter;

-- Existing snippets, including starters users have already received, are preserved.
COMMIT;
