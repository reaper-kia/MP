FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/search_service/pyproject.toml services/search_service/uv.lock ./

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

COPY . .

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin search \
    && chown -R search:search /app
USER search

CMD ["uvicorn", "search_service.main:app", "--host", "0.0.0.0", "--port", "8100"]