# Один образ на все Python-сервисы воркспейса; какой пакет ставить — build-arg PACKAGE:
#   docker build --build-arg PACKAGE=auth-service .
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /app
ARG PACKAGE

# Копируем воркспейс целиком (лишнее отрезает .dockerignore). Пересборка всё равно быстрая:
# скачанные колёса лежат в кэше uv между сборками (cache mount).
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --package "$PACKAGE"

ENV PATH="/app/.venv/bin:$PATH"
