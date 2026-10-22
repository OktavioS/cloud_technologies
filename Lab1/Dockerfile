# Базовий образ із зафіксованою версією (не latest)
FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1) Спочатку лише залежності — цей шар кешується, поки requirements.txt не змінився
COPY app/requirements.txt .
RUN pip install -r requirements.txt

# 2) Непривілейований користувач
RUN useradd --create-home --uid 10001 appuser

# 3) Код застосунку — останнім шаром, бо змінюється найчастіше
COPY --chown=appuser:appuser app/ .

USER appuser
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
