FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /app/services/ml_service

COPY packages/platform_contracts /app/packages/platform_contracts
COPY services/ml_service/pyproject.toml services/ml_service/uv.lock* services/ml_service/README.md ./

RUN uv sync --no-dev --no-install-project

COPY services/ml_service/src ./src

RUN uv sync --no-dev

ENV PATH="/app/services/ml_service/.venv/bin:$PATH"

EXPOSE 50055

CMD ["ml-service"]
