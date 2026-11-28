import os
from contextlib import closing, contextmanager

import psycopg2
from flask import g, has_request_context


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
RECENT_PERSONAL = "snippet_private.recent_personal_snippets"
RECENT_DEFAULT = "snippet_private.recent_default_snippets"
RECENTS_SQL = f"SELECT snippet_id, used_at FROM {RECENT_PERSONAL} UNION ALL SELECT snippet_id, used_at FROM {RECENT_DEFAULT}"
PERSONAL_SQL = "SELECT sno, name, cat, code, language, template FROM public.snippets WHERE owner_id = %s"
def visible_defaults_sql(extended=False):
    code = "coalesce(d.template_code, d.code)" if extended else "d.code"
    template = "d.template_code IS NOT NULL" if extended else "false"
    return f"""
        SELECT d.sno, d.name, d.cat, {code} AS code, d.language, {template} AS template
        FROM public.default_snippets d
        WHERE NOT EXISTS (
            SELECT 1 FROM snippet_private.hidden_default_snippets h WHERE h.user_id = %s AND h.snippet_id = d.sno
        )
    """


def connect():
    return psycopg2.connect(os.environ["SNIPPET_DATABASE_URL"], connect_timeout=5)


def close_request_connection(_error=None):
    conn = g.pop("snippet_connection", None)
    if conn is not None:
        conn.close()


@contextmanager
def transaction(conn, owner, verify):
    with conn, conn.cursor() as cur:
        if verify:
            cur.execute("SELECT current_user = 'snippet_app' AND session_user = 'snippet_app'")
            if not cur.fetchone()[0]:
                raise RuntimeError("The snippet_app database login is required")
        if owner is not None:
            cur.execute("SELECT set_config('snippet.owner_id', %s, true)", (owner,))
        yield cur


@contextmanager
def cursor(owner=None):
    if not has_request_context():
        with closing(connect()) as conn, transaction(conn, owner, verify=True) as cur:
            yield cur
        return

    conn = g.get("snippet_connection")
    verify = conn is None
    if verify:
        conn = g.snippet_connection = connect()
    try:
        with transaction(conn, owner, verify) as cur:
            yield cur
    except BaseException:
        # A later error handler may need to query again. Start with a fresh connection.
        close_request_connection()
        raise


def list_snippets(owner, search=None, category=None, include_categories=False, scope="all", sort="default",
                  include_favorites=False, extended=False, language=None):
    with cursor(owner) as cur:
        return select_snippets(cur, owner, search, category, include_categories, scope, sort, include_favorites,
                               extended=extended, language=language)


def library_page(owner, page, page_size, revision=None, **selection):
    with cursor(owner) as cur:
        rows, categories = select_snippets(cur, owner, include_categories=True, include_favorites=True,
                                           page=page, page_size=page_size, extended=True, **selection)
        total, current_revision = rows[0][-2:]
        if page > 1 and (rows[0][0] is None or revision not in (None, current_revision)):
            # Restart paging if another client changed the ordered result.
            page = 1
            rows, categories = select_snippets(cur, owner, include_categories=True, include_favorites=True,
                                               page=page, page_size=page_size, extended=True, **selection)
            total, current_revision = rows[0][-2:]
        recent = [row[:-4] for row in rows if row[-3]]
        visible = [row[:-4] for row in rows if row[0] is not None and not row[-3]]
        return visible, recent, categories, select_hidden_defaults(cur, owner), total, page, current_revision


def select_snippets(cur, owner, search=None, category=None, include_categories=False, scope="all", sort="default",
                    include_favorites=False, page=None, page_size=None, extended=False, language=None):
    defaults = visible_defaults_sql(extended)
    personal_and_defaults = PERSONAL_SQL + " UNION ALL " + defaults
    library, owners = {
        "all": (personal_and_defaults, (owner, owner)),
        "personal": (PERSONAL_SQL, (owner,)),
        "defaults": (defaults, (owner,)),
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
    if extended:
        fields += ", language, template"
    if extended and page is None:
        source += f" LEFT JOIN ({RECENTS_SQL}) AS recent ON recent.snippet_id = library.sno"
        fields += ", recent.used_at"
    sql = f"SELECT {fields} FROM {source} WHERE true"
    params = list(owners)
    if search:
        sql += " AND (name ILIKE %s OR code ILIKE %s)"
        params.extend([f"%{search}%"] * 2)
    if category:
        sql += " AND cat = %s"
        params.append(category)
    if language:
        sql += " AND language = %s"
        params.append(language)
    order = SNIPPET_ORDERS[sort]
    if page is None:
        sql += " ORDER BY " + order
    else:
        recent_group = "UNION ALL SELECT *, true FROM recent_rows" if page == 1 else ""
        sql = f"""WITH filtered AS ({sql}), recent_rows AS (
                    SELECT filtered.*, recent.used_at
                    FROM ({RECENTS_SQL}) AS recent JOIN filtered ON filtered.sno = recent.snippet_id
                    ORDER BY recent.used_at DESC, filtered.sno DESC LIMIT 5
                ), recent_meta AS (
                    SELECT count(*) AS size, coalesce(string_agg(sno::text, ',' ORDER BY sno), '') AS revision
                    FROM recent_rows
                ), page_rows AS (
                    (SELECT *, NULL::timestamptz AS used_at, false AS is_recent
                     FROM filtered WHERE sno NOT IN (SELECT sno FROM recent_rows)
                     ORDER BY {order}
                     LIMIT (%s - CASE WHEN %s THEN (SELECT size FROM recent_meta) ELSE 0 END)
                     OFFSET greatest(0, %s - (SELECT size FROM recent_meta)))
                    {recent_group}
                ), totals AS (
                    SELECT count(*) AS total,
                        md5(string_agg(sno::text, ',' ORDER BY {order}) || ':' ||
                            (SELECT revision FROM recent_meta)) AS revision
                    FROM filtered
                )
                SELECT page_rows.*, totals.total, totals.revision
                FROM totals LEFT JOIN page_rows ON true
                ORDER BY is_recent DESC, used_at DESC NULLS LAST, {order}"""
        params.extend((page_size, page == 1, (page - 1) * page_size))
    cur.execute(sql, params)
    rows = cur.fetchall()
    categories = []
    if include_categories:
        cur.execute(f"SELECT DISTINCT cat FROM {source} ORDER BY cat", owners)
        categories = cur.fetchall()
    return rows, categories

def get_snippet(owner, sno, extended=False):
    sql = visible_defaults_sql(extended) if sno >= DEFAULT_ID_MIN else PERSONAL_SQL
    with cursor(owner) as cur:
        columns = "sno, name, cat, code, language, template" if extended else "sno, name, cat, code"
        cur.execute(f"SELECT {columns} FROM ({sql}) AS library WHERE sno = %s", (owner, sno))
        return cur.fetchone()


def select_hidden_defaults(cur, owner):
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
    library = visible_defaults_sql() if shared else PERSONAL_SQL
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


def add_snippet(owner, name, cat, code, reject_duplicate=False, *, language=None, template=False):
    with cursor(owner) as cur:
        # Serialize same-name writes per user. Existing web saves can still use duplicate names.
        lock_snippet_name(cur, owner, name)
        if reject_duplicate:
            cur.execute("SELECT 1 FROM public.snippets WHERE owner_id = %s AND name = %s LIMIT 1", (owner, name))
            if cur.fetchone():
                return None
        cur.execute(
            "INSERT INTO public.snippets (owner_id, name, cat, code, language, template) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING sno",
            (owner, name, cat, code, language, template),
        )
        return cur.fetchone()[0]


def edit_snippet(owner, sno, name, cat, code, *, language=None, template=False):
    if sno >= DEFAULT_ID_MIN:
        return False
    with cursor(owner) as cur:
        lock_snippet_name(cur, owner, name)
        cur.execute("UPDATE public.snippets SET name = %s, cat = %s, code = %s, language = %s, template = %s "
                    "WHERE sno = %s AND owner_id = %s", (name, cat, code, language, template, sno, owner))
        return cur.rowcount == 1


def delete_snippet(owner, sno):
    if sno >= DEFAULT_ID_MIN:
        return False
    with cursor(owner) as cur:
        cur.execute("DELETE FROM public.snippets WHERE owner_id = %s AND sno = %s", (owner, sno))
        return cur.rowcount == 1


def record_recent(owner, sno):
    shared = sno >= DEFAULT_ID_MIN
    target = visible_defaults_sql() if shared else PERSONAL_SQL
    table = RECENT_DEFAULT if shared else RECENT_PERSONAL
    with cursor(owner) as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"snippet-recent:{owner}",))
        cur.execute(f"""
            INSERT INTO {table} (user_id, snippet_id, used_at)
            SELECT %s, sno, clock_timestamp() FROM ({target}) AS library WHERE sno = %s
            ON CONFLICT (user_id, snippet_id) DO UPDATE SET used_at = excluded.used_at
        """, (owner, owner, sno))
        if not cur.rowcount:
            return False
        cur.execute(f"""
            DELETE FROM {table} WHERE user_id = %s AND snippet_id IN (
                SELECT snippet_id FROM {table} WHERE user_id = %s
                ORDER BY used_at DESC, snippet_id DESC OFFSET 20
            )
        """, (owner, owner))
        return True


def category_counts(owner):
    with cursor(owner) as cur:
        cur.execute("SELECT cat, count(*) FROM public.snippets WHERE owner_id = %s GROUP BY cat ORDER BY cat",
                    (owner,))
        personal = cur.fetchall()
        cur.execute("SELECT DISTINCT cat FROM public.default_snippets ORDER BY cat")
        return personal, cur.fetchall()


def category_targets(cur, owner, source, ids, expected=None, destination=None):
    condition, values = ("sno = ANY(%s)", ids) if ids else ("cat = %s", source)
    selection = f"SELECT sno FROM public.snippets WHERE owner_id = %s AND {condition}"
    if expected is None:
        cur.execute(f"SELECT count(*) FROM ({selection}) AS targets", (owner, values))
    else:
        cur.execute(f"""
            WITH targets AS MATERIALIZED ({selection} ORDER BY sno FOR UPDATE),
            updated AS (
                UPDATE public.snippets SET cat = %s
                WHERE owner_id = %s AND sno IN (SELECT sno FROM targets)
                    AND (SELECT count(*) FROM targets) = %s
                RETURNING sno
            )
            SELECT count(*) FROM updated
        """, (owner, values, destination, owner, expected))
    return cur.fetchone()[0]
