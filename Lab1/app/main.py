import hmac
import json
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any

import psycopg
import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import cache
import db
import idempotency
import jobs
import settings
from auth import User, create_token, current_user, hash_password, verify_password
from metrics import counters, start_flusher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")


class State:
    pool = None
    kv: redis.Redis | None = None
    switch: cache.CacheSwitch | None = None
    sqs = None
    stop = threading.Event()


state = State()


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.pool = db.open_pool(settings.DB_POOL_MAX)
    db.migrate(state.pool)
    state.kv = cache.connect()
    state.switch = cache.CacheSwitch(state.kv)
    if jobs.enabled():
        state.sqs = jobs.sqs_client()
    start_flusher(settings.METRICS_NAMESPACE, settings.SERVICE_NAME, state.kv, settings.METRICS_FLUSH_SECONDS, state.stop)
    log.info("started version=%s redis=%s queue=%s", settings.APP_VERSION, state.kv is not None, state.sqs is not None)
    yield
    log.info("shutting down")
    state.stop.set()
    state.pool.close()


app = FastAPI(title="Notes API v3.0", version=settings.APP_VERSION, lifespan=lifespan)


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""


class CacheSwitchIn(BaseModel):
    enabled: bool


def require_redis() -> redis.Redis:
    if state.kv is None:
        raise HTTPException(503, "redis is not configured")
    return state.kv


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.ADMIN_TOKEN:
        raise HTTPException(404, "admin api disabled")
    if x_admin_token is None or not hmac.compare_digest(x_admin_token, settings.ADMIN_TOKEN):
        raise HTTPException(403, "wrong admin token")


@app.get("/")
def root():
    return {"service": "notes-api", "version": settings.APP_VERSION, "docs": "/docs"}


@app.get("/health")
def health():
    try:
        with state.pool.connection() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(503, f"db unavailable: {exc.__class__.__name__}")
    return {"status": "ok"}


@app.get("/debug/error")
def debug_error():
    raise HTTPException(500, "test error for the 5xx alarm")


@app.post("/auth/register", status_code=201, tags=["auth"])
def register(creds: Credentials):
    try:
        with state.pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id, username",
                (creds.username, hash_password(creds.password)),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "username already taken")
    return row


@app.post("/auth/login", tags=["auth"])
def login(creds: Credentials):
    with state.pool.connection() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = %s", (creds.username,)
        ).fetchone()
    if not row or not verify_password(creds.password, row["password_hash"]):
        raise HTTPException(401, "wrong username or password")
    return {
        "access_token": create_token(row["id"], creds.username),
        "token_type": "bearer",
        "user_id": row["id"],
    }


@app.get("/auth/me", tags=["auth"])
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username}


@app.get("/users/{user_id}", tags=["users"])
def get_user(user_id: int):
    with state.pool.connection() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.created_at,
                   (SELECT count(*) FROM notes n WHERE n.author_id = u.id) AS notes_count
            FROM users u WHERE u.id = %s
            """,
            (user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "user not found")
    return row


def load_notes_page(limit: int, offset: int) -> list[dict[str, Any]]:
    with state.pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, title, body, author_id, created_at FROM notes ORDER BY id DESC LIMIT %s OFFSET %s",
            (limit, offset),
        ).fetchall()
    return jsonable_encoder(rows)


@app.get("/notes", tags=["notes"])
def list_notes(
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    notes, source = cache.cache_aside(
        state.kv,
        state.switch,
        f"notes:list:{limit}:{offset}",
        settings.CACHE_TTL_SECONDS,
        lambda: load_notes_page(limit, offset),
    )
    response.headers["X-Cache"] = source
    return notes


@app.get("/notes/{note_id}", tags=["notes"])
def get_note(note_id: int):
    with state.pool.connection() as conn:
        row = conn.execute(
            "SELECT id, title, body, author_id, created_at FROM notes WHERE id = %s", (note_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    return row


def insert_note(note: NoteIn, author_id: int, request_id: str | None = None) -> dict[str, Any]:
    with state.pool.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO notes (title, body, author_id, request_id) VALUES (%s, %s, %s, %s)
            RETURNING id, title, body, author_id, created_at
            """,
            (note.title, note.body, author_id, request_id),
        ).fetchone()
    counters.inc("NotesCreated")
    return jsonable_encoder(row)


def replay_response(replay: idempotency.Replay) -> JSONResponse:
    counters.inc("IdempotentReplays")
    return JSONResponse(replay.body, status_code=replay.status, headers={"Idempotent-Replayed": "true"})


@app.post("/notes", status_code=201, tags=["notes"])
def create_note(
    note: NoteIn,
    user: User = Depends(current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if idempotency_key is None:
        return insert_note(note, user.id)
    scope = f"user:{user.id}"
    fp = idempotency.fingerprint({"op": "create_note", **note.model_dump()})
    replay = idempotency.begin(state.kv, scope, idempotency_key, fp)
    if replay is not None:
        return replay_response(replay)
    try:
        body = insert_note(note, user.id)
    except Exception:
        idempotency.abort(state.kv, scope, idempotency_key)
        raise
    idempotency.complete(state.kv, scope, idempotency_key, fp, 201, body)
    return body


@app.post("/notes/async", status_code=202, tags=["queue"])
def create_note_async(
    note: NoteIn,
    response: Response,
    user: User = Depends(current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if state.sqs is None:
        raise HTTPException(503, "queue is not configured")
    client = require_redis()
    scope = f"user:{user.id}"
    fp = idempotency.fingerprint({"op": "create_note_async", **note.model_dump()})
    if idempotency_key is not None:
        replay = idempotency.begin(client, scope, idempotency_key, fp)
        if replay is not None:
            return replay_response(replay)
    job_id = str(uuid.uuid4())
    body = {"job_id": job_id, "status": "queued", "status_url": f"/jobs/{job_id}"}
    try:
        jobs.save(client, job_id, {"job_id": job_id, "status": "queued", "owner_id": user.id})
        state.sqs.send_message(
            QueueUrl=jobs.queue_url(state.sqs),
            MessageBody=json.dumps({"job_id": job_id, "author_id": user.id, **note.model_dump()}),
        )
    except Exception:
        if idempotency_key is not None:
            idempotency.abort(client, scope, idempotency_key)
        raise
    counters.inc("JobsEnqueued")
    if idempotency_key is not None:
        idempotency.complete(client, scope, idempotency_key, fp, 202, body)
    response.headers["Location"] = body["status_url"]
    return body


@app.get("/jobs/{job_id}", tags=["queue"])
def get_job(job_id: uuid.UUID, user: User = Depends(current_user)):
    job = jobs.load(require_redis(), str(job_id))
    if job is None or job.get("owner_id") != user.id:
        raise HTTPException(404, "job not found")
    return job


@app.put("/notes/{note_id}", tags=["notes"])
def update_note(note_id: int, note: NoteIn, user: User = Depends(current_user)):
    with state.pool.connection() as conn:
        row = conn.execute(
            """
            UPDATE notes SET title = %s, body = %s WHERE id = %s AND author_id = %s
            RETURNING id, title, body, author_id, created_at
            """,
            (note.title, note.body, note_id, user.id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    return row


@app.delete("/notes/{note_id}", status_code=204, tags=["notes"])
def delete_note(note_id: int, user: User = Depends(current_user)):
    with state.pool.connection() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = %s AND author_id = %s", (note_id, user.id))
    if cur.rowcount == 0:
        raise HTTPException(404, "note not found")


@app.get("/admin/cache", tags=["admin"], dependencies=[Depends(require_admin)])
def cache_status():
    return {
        "redis": state.kv is not None,
        "enabled": state.switch.enabled(),
        "ttl_seconds": settings.CACHE_TTL_SECONDS,
    }


@app.put("/admin/cache", tags=["admin"], dependencies=[Depends(require_admin)])
def cache_set(payload: CacheSwitchIn):
    client = require_redis()
    state.switch.set(payload.enabled)
    if not payload.enabled:
        for key in client.scan_iter("notes:list:*"):
            client.delete(key)
    return {"enabled": payload.enabled}


@app.get("/admin/stats", tags=["admin"], dependencies=[Depends(require_admin)])
def stats():
    raw = require_redis().hgetall("stats")
    values = {name: int(value) for name, value in raw.items()}
    hits = values.get("CacheHits", 0)
    misses = values.get("CacheMisses", 0)
    lookups = hits + misses
    values["CacheHitRatio"] = round(hits / lookups, 4) if lookups else None
    return values


@app.delete("/admin/stats", status_code=204, tags=["admin"], dependencies=[Depends(require_admin)])
def stats_reset():
    require_redis().delete("stats")
