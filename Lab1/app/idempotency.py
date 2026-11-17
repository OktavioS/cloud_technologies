import hashlib
import json
from dataclasses import dataclass
from typing import Any

import redis
from fastapi import HTTPException

import settings

MAX_KEY_LENGTH = 128


@dataclass
class Replay:
    status: int
    body: Any


def fingerprint(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def redis_key(scope: str, key: str) -> str:
    return f"idem:{scope}:{key}"


def validate_key(key: str) -> None:
    if not 1 <= len(key) <= MAX_KEY_LENGTH:
        raise HTTPException(400, f"Idempotency-Key must be 1..{MAX_KEY_LENGTH} characters")


def begin(client: redis.Redis | None, scope: str, key: str, fp: str) -> Replay | None:
    if client is None:
        raise HTTPException(503, "idempotency store unavailable")
    validate_key(key)
    rkey = redis_key(scope, key)
    marker = json.dumps({"state": "processing", "fp": fp})
    try:
        if client.set(rkey, marker, nx=True, ex=settings.IDEMPOTENCY_TTL_SECONDS):
            return None
        raw = client.get(rkey)
    except redis.RedisError:
        raise HTTPException(503, "idempotency store unavailable")
    if raw is None:
        return begin(client, scope, key, fp)
    stored = json.loads(raw)
    if stored["fp"] != fp:
        raise HTTPException(422, "Idempotency-Key was already used with a different request body")
    if stored["state"] == "processing":
        raise HTTPException(409, "request with this Idempotency-Key is still in progress")
    return Replay(status=stored["status"], body=stored["body"])


def complete(client: redis.Redis, scope: str, key: str, fp: str, status: int, body: Any) -> None:
    record = json.dumps({"state": "done", "fp": fp, "status": status, "body": body}, default=str)
    client.set(redis_key(scope, key), record, ex=settings.IDEMPOTENCY_TTL_SECONDS)


def abort(client: redis.Redis, scope: str, key: str) -> None:
    try:
        client.delete(redis_key(scope, key))
    except redis.RedisError:
        pass
