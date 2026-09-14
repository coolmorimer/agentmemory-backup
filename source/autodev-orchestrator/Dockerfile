FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md ./
COPY apps/api ./apps/api
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY config ./config

EXPOSE 8000
CMD ["uvicorn", "autodev.main:app", "--host", "0.0.0.0", "--port", "8000"]

