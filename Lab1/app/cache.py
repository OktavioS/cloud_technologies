import json
import logging
import threading
import time
from typing import Any, Callable

import redis

import settings
from metrics import counters

log = logging.getLogger("cache")

FLAG_KEY = "config:cache_enabled"


def connect() -> redis.Redis | None:
    if not settings.REDIS_URL:
        return None
    return redis.Redis.from_url(
        settings.REDIS_URL,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
        socket_timeout=0.5,
        socket_connect_timeout=1,
        health_check_interval=30,
        retry_on_timeout=True,
    )


class CacheSwitch:
    def __init__(self, client: redis.Redis | None) -> None:
        self._client = client
        self._lock = threading.Lock()
        self._value = settings.CACHE_ENABLED_DEFAULT
        self._checked_at = 0.0

    def enabled(self) -> bool:
        if self._client is None:
            return False
        now = time.monotonic()
        if now - self._checked_at < settings.CACHE_FLAG_REFRESH_SECONDS:
            return self._value
        with self._lock:
            if now - self._checked_at >= settings.CACHE_FLAG_REFRESH_SECONDS:
                try:
                    raw = self._client.get(FLAG_KEY)
                    self._value = settings.CACHE_ENABLED_DEFAULT if raw is None else raw == "1"
                except redis.RedisError:
                    pass
                self._checked_at = now
        return self._value

    def set(self, enabled: bool) -> None:
        self._client.set(FLAG_KEY, "1" if enabled else "0")
        with self._lock:
            self._value = enabled
            self._checked_at = time.monotonic()


def cache_aside(
    client: redis.Redis | None,
    switch: CacheSwitch,
    key: str,
    ttl: int,
    loader: Callable[[], Any],
) -> tuple[Any, str]:
    if client is None or not switch.enabled():
        counters.inc("CacheBypass")
        counters.inc("DbQueries")
        return loader(), "BYPASS"
    try:
        cached = client.get(key)
    except redis.RedisError as exc:
        log.warning("cache read failed: %s", exc.__class__.__name__)
        cached = None
    if cached is not None:
        counters.inc("CacheHits")
        return json.loads(cached), "HIT"
    counters.inc("CacheMisses")
    counters.inc("DbQueries")
    value = loader()
    try:
        client.set(key, json.dumps(value, default=str), ex=ttl)
    except redis.RedisError as exc:
        log.warning("cache write failed: %s", exc.__class__.__name__)
    return value, "MISS"
