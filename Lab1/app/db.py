import os

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id            SERIAL PRIMARY KEY,
        username      TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notes (
        id         SERIAL PRIMARY KEY,
        title      TEXT NOT NULL,
        body       TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "ALTER TABLE notes ADD COLUMN IF NOT EXISTS author_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE notes ADD COLUMN IF NOT EXISTS request_id UUID UNIQUE",
    "CREATE INDEX IF NOT EXISTS notes_author_id_idx ON notes (author_id)",
]


def conninfo() -> str:
    return psycopg.conninfo.make_conninfo(
        host=os.environ["DB_HOST"],
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.getenv("DB_SSLMODE", "prefer"),
    )


def open_pool(max_size: int) -> ConnectionPool:
    pool = ConnectionPool(
        conninfo(),
        min_size=1,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    pool.wait(timeout=60)
    return pool


def migrate(pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(20261117)")
        for statement in SCHEMA:
            conn.execute(statement)
