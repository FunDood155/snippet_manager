# WP-11 — Editable shared default templates
**ID:** SNIPPO-WP11-DEFAULT-TEMPLATES
**Baseline:** main c2621ec42bb92f85e720b15fa0b5a6fa76fa6e5a, extension 1.1.0 (user confirms Marketplace live). Create feature/default-snippet-templates from latest main. Commit: `enable default snippet placeholders`.
**Objective:** make the four existing shared Python defaults editable native VS Code templates using the existing v2 API and 1.1.0 parser; no extension rebuild or Marketplace update expected.

## Verified current state
Live public.default_snippets contains IDs 2000000000 Hello World / Basics, 2000000001 Loop Through a List / Loops, 2000000002 Function Template / Functions, 2000000003 Exception Handling / Error Handling. All language values null. store.VISIBLE_DEFAULTS_SQL hardcodes false AS template. Existing extension consumes v=2 template=true and safe named {{identifier}} tokens, repeats share a tabstop. Web duplicate already propagates metadata; web copy of templates is intentionally literal.

## Implementation
- Preserve existing default IDs, names, categories and original runnable code, all personal data, hidden/favorite/recent references. Add nullable template_code to public.default_snippets (null means non-template). This avoids breaking legacy clients and old production during migration. Set language='python' and template_code for exactly four verified IDs through a new additive migration; do not overwrite unrelated admin edits: check expected old row contents and abort on mismatch. No new default rows. Keep shared table read-only for snippet_app; confirm SELECT grants cover new column only, no write rights. Admin can manage future defaults via Table Editor. Document valid syntax and admin workflow; validate all seeded template strings with existing valid_template and TS parser. No new parser syntax.
- For extended web/API reads, project COALESCE(template_code, code) AS code and template_code IS NOT NULL AS template, preserving identical tuple shapes and one-query paths. For legacy list/detail keep original code and exact response keys; search behavior consistent with the selected representation. Update shared SQL construction in store.py carefully for list/detail, scope, filters, recents, paging and duplication. Shared cards show Template and Python, web copy stays literal template text (as for personal templates), duplicate into editable personal snippet retains metadata; default remains read-only. Old backend remains compatible with additive schema.
- Seed templates (use LF; choose no triple braces, no arbitrary expressions). Preserve pedagogical purpose. The proposed exact templates follow:
```python
# Hello World (store without this label)
print("{{message}}")
```
```python
{{items}} = ["apple", "banana", "cherry"]

for {{item}} in {{items}}:
    print({{item}})
```
```python
def {{function_name}}({{parameter}}):
    return {{parameter}}

print({{function_name}}("Alex"))
```
```python
try:
    {{number}} = int(input("Enter a number: "))
    print({{number}})
except {{ValueError}}:
    print("{{error_message}}")
```
- Native repeated placeholders synchronize; Tab navigates distinct fields then final cursor. Default identifier text must yield syntactically valid Python after native substitution. Do not use f-string triple braces that current parser rejects. No change to personal template mode or extension source/version.

## Tests / gates
Run existing Python, callback JS, extension compile/lint/tests and focused disposable PostgreSQL regression: migration on existing four defaults, old backend and v1 list/detail unchanged, v2 list/detail true metadata/code, normal shared without template remains literal, hidden/favorite/recents and IDs preserved, shared writes rejected, personal duplicate template editable, web copy literal, language filter, pagination/count/search, owner isolation and no extra DB round trips. Verify four template strings with existing Python/TS validators and builder (repeated variable linked; safe escaping); actual desktop insertion/tab navigation is user acceptance if host unavailable. Keep Phase 3 performance and Tokyo hnd1. No live synthetic fixtures. Report tests actually run.
## Release
Activation authorizes scoped implementation, new migration preparation/testing and application to live Supabase only after isolated and old-backend compatibility tests pass, commit/push designated branch and verify resulting Preview. Inspect live rows/grants/branch first. Preserve exact original code and IDs, verify counts and existing prefs before/after; stop on mismatch. No merge/main write, manual production promotion, hosting changes, unrelated data changes or Marketplace publication. User merges after review. Report branch/SHA, files, migration version, all four template results, legacy compatibility, Vercel target/region, test results and limitations. If 1.1.0 cannot support this unchanged, stop and explain rather than bump version without revised scope.
