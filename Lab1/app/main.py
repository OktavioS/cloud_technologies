"""Notes API — простий REST API для лабораторної з хмарних технологій.

Конфігурація лише через змінні середовища (DB_HOST, DB_PORT, DB_NAME,
DB_USER, DB_PASSWORD, JWT_SECRET), секретів у коді немає.

Автентифікація (бонус 6): JWT, який видає і перевіряє сам сервіс.
- POST /auth/register — створити користувача
- POST /auth/login    — отримати токен
- POST/PUT/DELETE /notes — лише з заголовком "Authorization: Bearer <токен>",
  без нього відповідь 401.
"""
import hashlib
import hmac
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

APP_VERSION = os.getenv("APP_VERSION", "dev")
JWT_SECRET = os.environ["JWT_SECRET"]  # ключ підпису токенів: лише зі змінної середовища
JWT_ALGORITHM = "HS256"
JWT_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "60"))


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            SERIAL PRIMARY KEY,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    yield
    pool.close()


app = FastAPI(title="Notes API", version=APP_VERSION, lifespan=lifespan)


# ---------- Автентифікація ----------

def hash_password(password: str) -> str:
    """Пароль ніколи не зберігається як є — лише сіль + хеш PBKDF2."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split("$")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "iat": now, "exp": now + timedelta(minutes=JWT_TTL_MINUTES)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


bearer = HTTPBearer(auto_error=False)  # додає кнопку "Authorize" у Swagger


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    """Перевірка токена на стороні сервісу. Немає/поганий токен → 401."""
    unauthorized = {"WWW-Authenticate": "Bearer"}
    if creds is None:
        raise HTTPException(401, "missing token", headers=unauthorized)
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired", headers=unauthorized)
    except jwt.InvalidTokenError:
        raise HTTPException(401, "invalid token", headers=unauthorized)
    return payload["sub"]


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


@app.post("/auth/register", status_code=201, tags=["auth"])
def register(creds: Credentials):
    try:
        with pool.connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (creds.username, hash_password(creds.password)),
            )
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "username already taken")
    return {"username": creds.username}


@app.post("/auth/login", tags=["auth"])
def login(creds: Credentials):
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = %s", (creds.username,)
        ).fetchone()
    if not row or not verify_password(creds.password, row["password_hash"]):
        raise HTTPException(401, "wrong username or password")
    return {
        "access_token": create_token(creds.username),
        "token_type": "bearer",
        "expires_in": JWT_TTL_MINUTES * 60,
    }


@app.get("/auth/me", tags=["auth"])
def me(user: str = Depends(current_user)):
    return {"username": user}


# ---------- Службові ----------

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


@app.get("/debug/error")
def debug_error():
    """Навмисна помилка 500 — щоб на захисті показати алерт на 5xx (бонус 7)."""
    raise HTTPException(500, "test error for the 5xx alarm")


# ---------- Нотатки ----------
# Читати можуть усі; створювати, змінювати й видаляти — лише з токеном.

@app.get("/notes", tags=["notes"])
def list_notes():
    with pool.connection() as conn:
        return conn.execute("SELECT * FROM notes ORDER BY id").fetchall()


@app.get("/notes/{note_id}", tags=["notes"])
def get_note(note_id: int):
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = %s", (note_id,)).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    return row


@app.post("/notes", status_code=201, tags=["notes"])
def create_note(note: NoteIn, user: str = Depends(current_user)):
    with pool.connection() as conn:
        return conn.execute(
            "INSERT INTO notes (title, body) VALUES (%s, %s) RETURNING *",
            (note.title, note.body),
        ).fetchone()


@app.put("/notes/{note_id}", tags=["notes"])
def update_note(note_id: int, note: NoteIn, user: str = Depends(current_user)):
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE notes SET title = %s, body = %s WHERE id = %s RETURNING *",
            (note.title, note.body, note_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    return row


@app.delete("/notes/{note_id}", status_code=204, tags=["notes"])
def delete_note(note_id: int, user: str = Depends(current_user)):
    with pool.connection() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = %s", (note_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "note not found")
