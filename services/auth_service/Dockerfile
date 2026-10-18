FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /app/services/auth_service

COPY packages/platform_contracts /app/packages/platform_contracts
COPY services/auth_service/pyproject.toml services/auth_service/uv.lock* services/auth_service/README.md ./

RUN uv sync --no-dev --no-install-project

COPY services/auth_service/src ./src
COPY services/auth_service/alembic.ini ./
COPY services/auth_service/migrations ./migrations

RUN uv sync --no-dev

ENV PATH="/app/services/auth_service/.venv/bin:$PATH"

EXPOSE 50051

# сначала миграции, потом сервер
CMD ["sh", "-c", "alembic upgrade head && auth-service"]
