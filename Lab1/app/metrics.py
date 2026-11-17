import json
import logging
import threading
import time
from collections import defaultdict

log = logging.getLogger("metrics")


class Counters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, int] = defaultdict(int)

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._values[name] += amount

    def drain(self) -> dict[str, int]:
        with self._lock:
            values = dict(self._values)
            self._values.clear()
        return values


counters = Counters()


def emf_record(namespace: str, service: str, values: dict[str, int]) -> str:
    return json.dumps(
        {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": namespace,
                        "Dimensions": [["Service"]],
                        "Metrics": [{"Name": name, "Unit": "Count"} for name in values],
                    }
                ],
            },
            "Service": service,
            **values,
        }
    )


def flush(namespace: str, service: str, redis_client) -> None:
    values = counters.drain()
    if not values:
        return
    if namespace:
        print(emf_record(namespace, service, values), flush=True)
    if redis_client is not None:
        try:
            pipe = redis_client.pipeline()
            for name, amount in values.items():
                pipe.hincrby("stats", name, amount)
            pipe.execute()
        except Exception as exc:
            log.warning("stats flush to redis failed: %s", exc.__class__.__name__)


def start_flusher(namespace: str, service: str, redis_client, interval: float, stop: threading.Event) -> threading.Thread:
    def loop() -> None:
        while not stop.wait(interval):
            flush(namespace, service, redis_client)
        flush(namespace, service, redis_client)

    thread = threading.Thread(target=loop, name="metrics-flusher", daemon=True)
    thread.start()
    return thread
