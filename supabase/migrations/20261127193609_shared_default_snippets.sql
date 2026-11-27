BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '20s';

-- Keep the personal sequence in place and reserve the upper range for defaults.
ALTER TABLE public.snippets ADD CONSTRAINT snippets_personal_id_range
    CHECK (sno < 2000000000);
ALTER SEQUENCE public.snippets_sno_seq MAXVALUE 1999999999 NO CYCLE;
DO $$
BEGIN
    IF (SELECT last_value FROM public.snippets_sno_seq) >= 2000000000 THEN
        RAISE EXCEPTION 'Personal sequence has reached the reserved shared range';
    END IF;
END $$;

CREATE TABLE public.default_snippets (
    sno integer GENERATED ALWAYS AS IDENTITY (START WITH 2000000000 MINVALUE 2000000000
                                               MAXVALUE 2147483647 NO CYCLE) PRIMARY KEY,
    name text NOT NULL,
    cat text NOT NULL,
    code text NOT NULL,
    CONSTRAINT default_snippets_id_range CHECK (sno >= 2000000000)
);
REVOKE ALL ON public.default_snippets
    FROM PUBLIC, anon, authenticated, service_role, snippet_app;
REVOKE ALL ON SEQUENCE public.default_snippets_sno_seq
    FROM PUBLIC, anon, authenticated, service_role, snippet_app;
ALTER TABLE public.default_snippets ENABLE ROW LEVEL SECURITY;
GRANT SELECT ON public.default_snippets TO snippet_app;
CREATE POLICY default_snippets_select ON public.default_snippets FOR SELECT TO snippet_app
    USING (nullif(current_setting('snippet.owner_id', true), '')::uuid IS NOT NULL);

INSERT INTO public.default_snippets (name, cat, code) VALUES
        ('Hello World', 'Basics', 'print("Hello, world!")'),
        ('Loop Through a List', 'Loops', $python$items = ["apple", "banana", "cherry"]
for item in items:
    print(item)$python$),
        ('Function Template', 'Functions', $python$def greet(name):
    return f"Hello, {name}!"

print(greet("Alex"))$python$),
        ('Exception Handling', 'Error Handling', $python$try:
    number = int(input("Enter a whole number: "))
    print(f"You entered {number}.")
except ValueError:
    print("Please enter a valid whole number.")$python$);

COMMIT;
