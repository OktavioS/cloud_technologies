import json
import logging
import signal
import threading
import time

import cache
import db
import jobs
import settings
from metrics import counters, start_flusher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")

INSERT = """
INSERT INTO notes (title, body, author_id, request_id) VALUES (%s, %s, %s, %s)
ON CONFLICT (request_id) DO NOTHING
RETURNING id, title, body, author_id, created_at
"""
SELECT_EXISTING = "SELECT id, title, body, author_id, created_at FROM notes WHERE request_id = %s"


def process(pool, redis_client, message: dict) -> None:
    job_id = message["job_id"]
    if settings.WORK_DELAY_MS:
        time.sleep(settings.WORK_DELAY_MS / 1000)
    with pool.connection() as conn:
        row = conn.execute(INSERT, (message["title"], message.get("body", ""), message["author_id"], job_id)).fetchone()
        duplicate = row is None
        if duplicate:
            row = conn.execute(SELECT_EXISTING, (job_id,)).fetchone()
    row = {**row, "created_at": row["created_at"].isoformat()}
    counters.inc("JobsDuplicate" if duplicate else "JobsProcessed")
    if not duplicate:
        counters.inc("NotesCreated")
    if redis_client is not None:
        jobs.save(
            redis_client,
            job_id,
            {"job_id": job_id, "status": "done", "owner_id": message["author_id"], "note": row, "duplicate": duplicate},
        )
    log.info("job %s done note=%s duplicate=%s", job_id, row["id"], duplicate)


def main() -> None:
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    pool = db.open_pool(settings.DB_POOL_MAX)
    db.migrate(pool)
    redis_client = cache.connect()
    sqs = jobs.sqs_client()
    url = None
    while url is None and not stop.is_set():
        try:
            url = jobs.queue_url(sqs)
        except Exception as exc:
            log.warning("queue not ready: %s", exc.__class__.__name__)
            stop.wait(2)
    flusher_stop = threading.Event()
    flusher = start_flusher(settings.METRICS_NAMESPACE, "worker", redis_client, settings.METRICS_FLUSH_SECONDS, flusher_stop)
    log.info("worker started version=%s queue=%s", settings.APP_VERSION, url)

    while not stop.is_set():
        try:
            response = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=10)
        except Exception as exc:
            log.warning("receive failed: %s", exc.__class__.__name__)
            stop.wait(2)
            continue
        for message in response.get("Messages", []):
            try:
                process(pool, redis_client, json.loads(message["Body"]))
            except Exception:
                counters.inc("JobsFailed")
                log.exception("job failed, message will be redelivered")
                continue
            sqs.delete_message(QueueUrl=url, ReceiptHandle=message["ReceiptHandle"])

    log.info("worker stopping")
    flusher_stop.set()
    flusher.join(timeout=5)
    pool.close()


if __name__ == "__main__":
    main()
