FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /app/services/gateway

COPY packages/platform_contracts /app/packages/platform_contracts
COPY services/gateway/pyproject.toml services/gateway/uv.lock* services/gateway/README.md ./

RUN uv sync --no-dev --no-install-project

COPY services/gateway/src ./src

RUN uv sync --no-dev

ENV PATH="/app/services/gateway/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
