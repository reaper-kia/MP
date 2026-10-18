FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /app/services/example_service

COPY packages/platform_contracts /app/packages/platform_contracts
COPY services/example_service/pyproject.toml services/example_service/uv.lock* services/example_service/README.md ./

RUN uv sync --no-dev --no-install-project

COPY services/example_service/src ./src
COPY services/example_service/alembic.ini ./
COPY services/example_service/migrations ./migrations

RUN uv sync --no-dev

ENV PATH="/app/services/example_service/.venv/bin:$PATH"

EXPOSE 50052

# сначала миграции, потом сервер
CMD ["sh", "-c", "alembic upgrade head && example-service"]
