BEGIN;

CREATE ROLE snippet_starter NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

CREATE TABLE snippet_private.pending_starter_accounts (
    user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE
);
REVOKE ALL ON snippet_private.pending_starter_accounts FROM PUBLIC, anon, authenticated, service_role, snippet_app;
GRANT USAGE ON SCHEMA public, snippet_private TO snippet_starter;
GRANT SELECT (user_id), INSERT (user_id) ON snippet_private.pending_starter_accounts TO snippet_starter;
GRANT DELETE ON snippet_private.pending_starter_accounts TO snippet_starter;
GRANT INSERT (owner_id, name, cat, code) ON public.snippets TO snippet_starter;
GRANT USAGE ON SEQUENCE public.snippets_sno_seq TO snippet_starter;

CREATE POLICY snippets_insert_starters ON public.snippets FOR INSERT TO snippet_starter
    WITH CHECK (owner_id = nullif(current_setting('snippet.owner_id', true), '')::uuid);

CREATE FUNCTION snippet_private.provision_starter_snippets()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    previous_owner text;
BEGIN
    -- Track new accounts only. Existing unconfirmed accounts have no pending row.
    IF TG_OP = 'INSERT' THEN
        INSERT INTO snippet_private.pending_starter_accounts (user_id) VALUES (NEW.id);
    END IF;

    IF NEW.email_confirmed_at IS NULL THEN
        RETURN NEW;
    END IF;

    -- Claim provisioning and insert all four snippets in the same transaction.
    DELETE FROM snippet_private.pending_starter_accounts WHERE user_id = NEW.id;
    IF NOT FOUND THEN
        RETURN NEW;
    END IF;

    previous_owner := pg_catalog.current_setting('snippet.owner_id', true);
    PERFORM pg_catalog.set_config('snippet.owner_id', NEW.id::text, true);
    INSERT INTO public.snippets (owner_id, name, cat, code) VALUES
        (NEW.id, 'Hello World', 'Basics', 'print("Hello, world!")'),
        (NEW.id, 'Loop Through a List', 'Loops', $python$items = ["apple", "banana", "cherry"]
for item in items:
    print(item)$python$),
        (NEW.id, 'Function Template', 'Functions', $python$def greet(name):
    return f"Hello, {name}!"

print(greet("Alex"))$python$),
        (NEW.id, 'Exception Handling', 'Error Handling', $python$try:
    number = int(input("Enter a whole number: "))
    print(f"You entered {number}.")
except ValueError:
    print("Please enter a valid whole number.")$python$);
    PERFORM pg_catalog.set_config('snippet.owner_id', coalesce(previous_owner, ''), true);
    RETURN NEW;
END
$$;

REVOKE ALL ON FUNCTION snippet_private.provision_starter_snippets() FROM PUBLIC, anon, authenticated, service_role, snippet_app;
CREATE TRIGGER snippet_starter_accounts
    AFTER INSERT OR UPDATE OF email_confirmed_at ON auth.users
    FOR EACH ROW EXECUTE FUNCTION snippet_private.provision_starter_snippets();

-- Function ownership requires the migration role to be able to SET ROLE to its new owner.
GRANT snippet_starter TO CURRENT_USER WITH SET TRUE;
GRANT CREATE ON SCHEMA snippet_private TO snippet_starter;
ALTER FUNCTION snippet_private.provision_starter_snippets() OWNER TO snippet_starter;
REVOKE CREATE ON SCHEMA snippet_private FROM snippet_starter;
REVOKE SET OPTION FOR snippet_starter FROM CURRENT_USER;

COMMIT;
