FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /app/services/search_service

COPY packages/platform_contracts /app/packages/platform_contracts
COPY services/search_service/pyproject.toml services/search_service/uv.lock* services/search_service/README.md ./

RUN uv sync --no-dev --no-install-project

COPY services/search_service/src ./src
COPY services/search_service/alembic.ini ./
COPY services/search_service/migrations ./migrations

RUN uv sync --no-dev

ENV PATH="/app/services/search_service/.venv/bin:$PATH"

EXPOSE 50053

# сначала миграции, потом сервер
CMD ["sh", "-c", "alembic upgrade head && search-service"]
