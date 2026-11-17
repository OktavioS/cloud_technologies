import json
import threading
from typing import Any

import boto3
import redis

import settings

_lock = threading.Lock()
_queue_url: str | None = None


def enabled() -> bool:
    return bool(settings.SQS_QUEUE_URL or settings.SQS_QUEUE_NAME)


def sqs_client():
    return boto3.client("sqs", region_name=settings.AWS_REGION, endpoint_url=settings.SQS_ENDPOINT_URL)


def queue_url(client) -> str:
    global _queue_url
    if settings.SQS_QUEUE_URL:
        return settings.SQS_QUEUE_URL
    with _lock:
        if _queue_url is None:
            _queue_url = client.create_queue(QueueName=settings.SQS_QUEUE_NAME)["QueueUrl"]
    return _queue_url


def job_key(job_id: str) -> str:
    return f"job:{job_id}"


def save(client: redis.Redis, job_id: str, data: dict[str, Any]) -> None:
    client.set(job_key(job_id), json.dumps(data, default=str), ex=settings.JOB_TTL_SECONDS)


def load(client: redis.Redis, job_id: str) -> dict[str, Any] | None:
    raw = client.get(job_key(job_id))
    return None if raw is None else json.loads(raw)
