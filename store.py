import os
from contextlib import closing, contextmanager

import psycopg2


@contextmanager
def cursor(owner=None):
    # This DSN must authenticate as the dedicated NOINHERIT runtime role.
    with closing(psycopg2.connect(os.environ["SNIPPET_DATABASE_URL"], connect_timeout=5)) as conn:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT current_user = 'snippet_app' AND session_user = 'snippet_app'")
            if not cur.fetchone()[0]:
                raise RuntimeError("The snippet_app database login is required")
            if owner is not None:
                cur.execute("SELECT set_config('snippet.owner_id', %s, true)", (owner,))
            yield cur


def list_snippets(owner, search=None, category=None, include_categories=False):
    with cursor(owner) as cur:
        sql = "SELECT sno, name, cat, code FROM public.snippets WHERE owner_id = %s"
        params = [owner]
        if search:
            sql += " AND (name ILIKE %s OR code ILIKE %s)"
            params.extend([f"%{search}%"] * 2)
        if category:
            sql += " AND cat = %s"
            params.append(category)
        cur.execute(sql + " ORDER BY sno", params)
        rows = cur.fetchall()
        categories = []
        if include_categories:
            cur.execute("SELECT DISTINCT cat FROM public.snippets WHERE owner_id = %s ORDER BY cat", (owner,))
            categories = cur.fetchall()
        return rows, categories


def get_snippet(owner, sno):
    with cursor(owner) as cur:
        cur.execute("SELECT sno, name, cat, code FROM public.snippets WHERE owner_id = %s AND sno = %s", (owner, sno))
        return cur.fetchone()


def add_snippet(owner, name, cat, code, reject_duplicate=False):
    with cursor(owner) as cur:
        # Serialize same-name writes per user. Existing web saves can still use duplicate names.
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"{owner}:{name}",))
        if reject_duplicate:
            cur.execute("SELECT 1 FROM public.snippets WHERE owner_id = %s AND name = %s LIMIT 1", (owner, name))
            if cur.fetchone():
                return None
        cur.execute(
            "INSERT INTO public.snippets (owner_id, name, cat, code) VALUES (%s, %s, %s, %s) RETURNING sno",
            (owner, name, cat, code),
        )
        return cur.fetchone()[0]


def delete_snippet(owner, sno):
    with cursor(owner) as cur:
        cur.execute("DELETE FROM public.snippets WHERE owner_id = %s AND sno = %s", (owner, sno))
        return cur.rowcount == 1
