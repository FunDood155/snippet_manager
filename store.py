import os
from contextlib import closing, contextmanager

import psycopg2


DEFAULT_ID_MIN = 2_000_000_000
PERSONAL_SQL = "SELECT sno, name, cat, code FROM public.snippets WHERE owner_id = %s"
VISIBLE_DEFAULTS_SQL = """
    SELECT d.sno, d.name, d.cat, d.code FROM public.default_snippets d
    WHERE NOT EXISTS (
        SELECT 1 FROM snippet_private.hidden_default_snippets h WHERE h.user_id = %s AND h.snippet_id = d.sno
    )
"""


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


def list_snippets(owner, search=None, category=None, include_categories=False, scope="all"):
    library, owners = {
        "all": (PERSONAL_SQL + " UNION ALL " + VISIBLE_DEFAULTS_SQL, (owner, owner)),
        "personal": (PERSONAL_SQL, (owner,)),
        "defaults": (VISIBLE_DEFAULTS_SQL, (owner,)),
    }[scope]
    with cursor(owner) as cur:
        sql = f"SELECT sno, name, cat, code FROM ({library}) AS library WHERE true"
        params = list(owners)
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
            cur.execute(f"SELECT DISTINCT cat FROM ({library}) AS library ORDER BY cat", owners)
            categories = cur.fetchall()
        return rows, categories


def get_snippet(owner, sno):
    sql = VISIBLE_DEFAULTS_SQL if sno >= DEFAULT_ID_MIN else PERSONAL_SQL
    with cursor(owner) as cur:
        cur.execute(f"SELECT sno, name, cat, code FROM ({sql}) AS library WHERE sno = %s", (owner, sno))
        return cur.fetchone()


def hidden_defaults(owner):
    with cursor(owner) as cur:
        cur.execute("""
            SELECT d.sno, d.name, d.cat FROM public.default_snippets d
            JOIN snippet_private.hidden_default_snippets h ON h.snippet_id = d.sno
            WHERE h.user_id = %s ORDER BY d.sno
        """, (owner,))
        return cur.fetchall()


def hide_default(owner, sno):
    with cursor(owner) as cur:
        cur.execute("""
            WITH target AS (SELECT sno FROM public.default_snippets WHERE sno = %s),
            inserted AS (
                INSERT INTO snippet_private.hidden_default_snippets (user_id, snippet_id)
                SELECT %s, sno FROM target ON CONFLICT (user_id, snippet_id) DO NOTHING
            )
            SELECT EXISTS (SELECT 1 FROM target)
        """, (sno, owner))
        return cur.fetchone()[0]


def restore_default(owner, sno):
    with cursor(owner) as cur:
        cur.execute("""
            WITH target AS (SELECT sno FROM public.default_snippets WHERE sno = %s),
            removed AS (
                DELETE FROM snippet_private.hidden_default_snippets h
                USING target WHERE h.user_id = %s AND h.snippet_id = target.sno
            )
            SELECT EXISTS (SELECT 1 FROM target)
        """, (sno, owner))
        return cur.fetchone()[0]


def restore_all_defaults(owner):
    with cursor(owner) as cur:
        cur.execute("DELETE FROM snippet_private.hidden_default_snippets WHERE user_id = %s", (owner,))
        return cur.rowcount

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
    if sno >= DEFAULT_ID_MIN:
        return False
    with cursor(owner) as cur:
        cur.execute("DELETE FROM public.snippets WHERE owner_id = %s AND sno = %s", (owner, sno))
        return cur.rowcount == 1
