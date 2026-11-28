"""The pre-authentication SQLite importer is retired.

Current installations use the versioned Supabase SQL migrations. The old
schema assumed snippets had no owner and is unsuitable for current databases.
"""


if __name__ == "__main__":
    raise SystemExit("The legacy SQLite importer is retired. See docs/authentication.md for database setup.")
