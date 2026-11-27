import os
from contextlib import closing, contextmanager

import psycopg2


DEFAULT_ID_MIN = 2_000_000_000
PERSONAL_FAVORITES = "snippet_private.favorite_personal_snippets"
DEFAULT_FAVORITES = "snippet_private.favorite_default_snippets"
FAVORITES_SQL = f"""
    SELECT snippet_id FROM {PERSONAL_FAVORITES}
    UNION ALL
    SELECT snippet_id FROM {DEFAULT_FAVORITES}
"""
SNIPPET_ORDERS = {
    "default": "sno",
    "name": "lower(name), sno",
    "newest": f"(sno >= {DEFAULT_ID_MIN}), sno DESC",
    "oldest": f"(sno >= {DEFAULT_ID_MIN}), sno ASC",
}
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


def list_snippets(owner, search=None, category=None, include_categories=False, scope="all", sort="default",
                  include_favorites=False):
    personal_and_defaults = PERSONAL_SQL + " UNION ALL " + VISIBLE_DEFAULTS_SQL
    library, owners = {
        "all": (personal_and_defaults, (owner, owner)),
        "personal": (PERSONAL_SQL, (owner,)),
        "defaults": (VISIBLE_DEFAULTS_SQL, (owner,)),
        "favorites": (personal_and_defaults, (owner, owner)),
    }[scope]
    favorite_only = scope == "favorites"
    source = f"({library}) AS library"
    if favorite_only or include_favorites:
        join = "JOIN" if favorite_only else "LEFT JOIN"
        source += f" {join} ({FAVORITES_SQL}) AS favorites ON favorites.snippet_id = library.sno"
    fields = "sno, name, cat, code"
    if include_favorites:
        fields += ", favorites.snippet_id IS NOT NULL"
    with cursor(owner) as cur:
        sql = f"SELECT {fields} FROM {source} WHERE true"
        params = list(owners)
        if search:
            sql += " AND (name ILIKE %s OR code ILIKE %s)"
            params.extend([f"%{search}%"] * 2)
        if category:
            sql += " AND cat = %s"
            params.append(category)
        cur.execute(sql + " ORDER BY " + SNIPPET_ORDERS[sort], params)
        rows = cur.fetchall()
        categories = []
        if include_categories:
            cur.execute(f"SELECT DISTINCT cat FROM {source} ORDER BY cat", owners)
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


def set_favorite(owner, sno, favorite):
    shared = sno >= DEFAULT_ID_MIN
    library = VISIBLE_DEFAULTS_SQL if shared else PERSONAL_SQL
    table = DEFAULT_FAVORITES if shared else PERSONAL_FAVORITES
    change = (
        f"INSERT INTO {table} (user_id, snippet_id) SELECT %s, sno FROM target ON CONFLICT DO NOTHING"
        if favorite else
        f"DELETE FROM {table} f USING target WHERE f.user_id = %s AND f.snippet_id = target.sno"
    )
    with cursor(owner) as cur:
        cur.execute(f"""
            WITH target AS (SELECT sno FROM ({library}) AS library WHERE sno = %s),
            changed AS ({change})
            SELECT EXISTS (SELECT 1 FROM target)
        """, (owner, sno, owner))
        return cur.fetchone()[0]


def lock_snippet_name(cur, owner, name):
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"{owner}:{name}",))


def add_snippet(owner, name, cat, code, reject_duplicate=False):
    with cursor(owner) as cur:
        # Serialize same-name writes per user. Existing web saves can still use duplicate names.
        lock_snippet_name(cur, owner, name)
        if reject_duplicate:
            cur.execute("SELECT 1 FROM public.snippets WHERE owner_id = %s AND name = %s LIMIT 1", (owner, name))
            if cur.fetchone():
                return None
        cur.execute(
            "INSERT INTO public.snippets (owner_id, name, cat, code) VALUES (%s, %s, %s, %s) RETURNING sno",
            (owner, name, cat, code),
        )
        return cur.fetchone()[0]


def edit_snippet(owner, sno, name, cat, code):
    if sno >= DEFAULT_ID_MIN:
        return False
    with cursor(owner) as cur:
        lock_snippet_name(cur, owner, name)
        cur.execute("UPDATE public.snippets SET name = %s, cat = %s, code = %s WHERE sno = %s AND owner_id = %s",
                    (name, cat, code, sno, owner))
        return cur.rowcount == 1


def delete_snippet(owner, sno):
    if sno >= DEFAULT_ID_MIN:
        return False
    with cursor(owner) as cur:
        cur.execute("DELETE FROM public.snippets WHERE owner_id = %s AND sno = %s", (owner, sno))
        return cur.rowcount == 1
