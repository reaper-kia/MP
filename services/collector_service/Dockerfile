FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /app/services/collector_service

COPY packages/platform_contracts /app/packages/platform_contracts
COPY services/collector_service/pyproject.toml services/collector_service/uv.lock* services/collector_service/README.md ./

RUN uv sync --no-dev --no-install-project

COPY services/collector_service/src ./src

RUN uv sync --no-dev

ENV PATH="/app/services/collector_service/.venv/bin:$PATH"

EXPOSE 50054

CMD ["collector-service"]
