"""Notes API — простий REST API для лабораторної з хмарних технологій.

Конфігурація лише через змінні середовища (DB_HOST, DB_PORT, DB_NAME,
DB_USER, DB_PASSWORD), секретів у коді немає.
"""
import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

APP_VERSION = os.getenv("APP_VERSION", "dev")


def conninfo() -> str:
    return psycopg.conninfo.make_conninfo(
        host=os.environ["DB_HOST"],
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.getenv("DB_SSLMODE", "prefer"),
    )


pool: ConnectionPool | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool
    pool = ConnectionPool(conninfo(), min_size=1, max_size=5, kwargs={"row_factory": dict_row})
    pool.wait(timeout=30)
    with pool.connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id         SERIAL PRIMARY KEY,
                title      TEXT NOT NULL,
                body       TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    yield
    pool.close()


app = FastAPI(title="Notes API", version=APP_VERSION, lifespan=lifespan)


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""


@app.get("/")
def root():
    return {"service": "notes-api", "version": APP_VERSION, "docs": "/docs"}


@app.get("/health")
def health():
    """Health check для балансувальника: перевіряє і процес, і з'єднання з БД."""
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"db unavailable: {exc.__class__.__name__}")
    return {"status": "ok"}


@app.get("/notes")
def list_notes():
    with pool.connection() as conn:
        return conn.execute("SELECT * FROM notes ORDER BY id").fetchall()


@app.get("/notes/{note_id}")
def get_note(note_id: int):
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = %s", (note_id,)).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    return row


@app.post("/notes", status_code=201)
def create_note(note: NoteIn):
    with pool.connection() as conn:
        return conn.execute(
            "INSERT INTO notes (title, body) VALUES (%s, %s) RETURNING *",
            (note.title, note.body),
        ).fetchone()


@app.put("/notes/{note_id}")
def update_note(note_id: int, note: NoteIn):
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE notes SET title = %s, body = %s WHERE id = %s RETURNING *",
            (note.title, note.body, note_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    return row


@app.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int):
    with pool.connection() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = %s", (note_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "note not found")
