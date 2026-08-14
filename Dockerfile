# MindMesh app container. TradingAgents is installed from a pinned git SHA
# (EXECUTION_PLAN.md D3/D8/F3) — the source is never COPYed, so the TradingAgents/.env
# secret can never enter the build context. Runs as a non-root user (§13).

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Non-root user first (read-only container best-effort; see main.py headers).
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data && chown -R app:app /app

WORKDIR /app

# Git is required to install the deep-mode dependency from a pinned SHA.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

# Install the app and its deep-mode dependency (TradingAgents @ pinned SHA).
RUN pip install --upgrade pip \
    && pip install . ".[deep]"

USER app

EXPOSE 8000

# Read-only filesystem where possible; /app/data is the one writable mount.
VOLUME ["/app/data"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]