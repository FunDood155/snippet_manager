BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '20s';

-- Keep runnable source for older clients. This column is only used by template-aware reads.
ALTER TABLE public.default_snippets ADD COLUMN template_code text;

DO $$
DECLARE
    updated integer;
BEGIN
    UPDATE public.default_snippets AS defaults
    SET language = 'python', template_code = seed.template_code
    FROM (VALUES
        (2000000000, 'Hello World', 'Basics', $python$print("Hello, world!")$python$,
            $python$print("{{message}}")$python$),
        (2000000001, 'Loop Through a List', 'Loops', $python$items = ["apple", "banana", "cherry"]
for item in items:
    print(item)$python$,
            $python${{items}} = ["apple", "banana", "cherry"]

for {{item}} in {{items}}:
    print({{item}})$python$),
        (2000000002, 'Function Template', 'Functions', $python$def greet(name):
    return f"Hello, {name}!"

print(greet("Alex"))$python$,
            $python$def {{function_name}}({{parameter}}):
    return {{parameter}}

print({{function_name}}("Alex"))$python$),
        (2000000003, 'Exception Handling', 'Error Handling', $python$try:
    number = int(input("Enter a whole number: "))
    print(f"You entered {number}.")
except ValueError:
    print("Please enter a valid whole number.")$python$,
            $python$try:
    {{number}} = int(input("Enter a number: "))
    print({{number}})
except {{ValueError}}:
    print("{{error_message}}")$python$)
    ) AS seed(sno, name, cat, code, template_code)
    WHERE defaults.sno = seed.sno
      AND (defaults.name, defaults.cat, defaults.code) = (seed.name, seed.cat, seed.code)
      AND defaults.language IS NULL;

    GET DIAGNOSTICS updated = ROW_COUNT;
    IF updated <> 4 THEN
        RAISE EXCEPTION 'Shared default snippets differ from the reviewed originals';
    END IF;
END $$;

COMMIT;
