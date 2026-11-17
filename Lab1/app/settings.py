import os


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


APP_VERSION = os.getenv("APP_VERSION", "dev")
SERVICE_NAME = os.getenv("SERVICE_NAME", "app")

DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

REDIS_URL = os.getenv("REDIS_URL", "")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

CACHE_ENABLED_DEFAULT = env_bool("CACHE_ENABLED", True)
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "30"))
CACHE_FLAG_REFRESH_SECONDS = float(os.getenv("CACHE_FLAG_REFRESH_SECONDS", "5"))

IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", str(24 * 3600)))
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", str(24 * 3600)))

AWS_REGION = os.getenv("AWS_REGION", "eu-north-1")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
SQS_QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "")
SQS_ENDPOINT_URL = os.getenv("SQS_ENDPOINT_URL") or None
WORK_DELAY_MS = int(os.getenv("WORK_DELAY_MS", "0"))

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

METRICS_NAMESPACE = os.getenv("METRICS_NAMESPACE", "")
METRICS_FLUSH_SECONDS = float(os.getenv("METRICS_FLUSH_SECONDS", "10"))
