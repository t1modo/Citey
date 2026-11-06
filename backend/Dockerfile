# syntax=docker/dockerfile:1

# ---- Build: install locked dependencies with uv ---------------------------
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.9.11 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, so editing the code reuses this layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project

# ---- Runtime: the virtualenv and the app, no uv ---------------------------
FROM python:3.12-slim
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app

RUN useradd --create-home --uid 10001 citey
COPY --from=build /app/.venv /app/.venv
COPY --chown=citey:citey main.py ./
COPY --chown=citey:citey app ./app
COPY --chown=citey:citey templates ./templates
USER citey

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/api/health\", timeout=4)"]
# PORT lets hosts that assign one (Render, Cloud Run) use the same image.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
