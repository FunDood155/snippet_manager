import sqlite3
import psycopg2
import os

# -----------------------------
# SQLite
# -----------------------------

sqlite_conn = sqlite3.connect("snippets.db")
sqlite_cursor = sqlite_conn.cursor()

sqlite_cursor.execute(
    "SELECT sno, name, cat, code FROM snippets"
)

snippets = sqlite_cursor.fetchall()

sqlite_conn.close()

print(f"Found {len(snippets)} snippets in SQLite.")


# -----------------------------
# PostgreSQL
# -----------------------------

database_url = os.environ["DATABASE_URL"]

pg_conn = psycopg2.connect(database_url)
pg_cursor = pg_conn.cursor()


# -----------------------------
# Insert into PostgreSQL
# -----------------------------

for snippet in snippets:
    pg_cursor.execute(
        """
        INSERT INTO snippets (sno, name, cat, code)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (sno) DO NOTHING
        """,
        snippet
    )

pg_conn.commit()


# -----------------------------
# Fix ID sequence
# -----------------------------

pg_cursor.execute(
    """
    SELECT setval(
        pg_get_serial_sequence('snippets', 'sno'),
        COALESCE(MAX(sno), 1),
        MAX(sno) IS NOT NULL
    )
    FROM snippets
    """
)

pg_conn.commit()

pg_cursor.close()
pg_conn.close()

print("Migration completed successfully.")