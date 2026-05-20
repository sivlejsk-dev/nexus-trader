# ── Stage 1: dependency builder ───────────────────────────────────────────────
# Compile wheels in a full image so the final stage stays slim.
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps needed to compile C-extension wheels (numpy, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN addgroup --system nexus && adduser --system --ingroup nexus nexus

WORKDIR /app

# Install pre-built wheels — no compiler needed in the final image
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* \
 && rm -rf /wheels

# Copy application source
COPY --chown=nexus:nexus . .

# Persistent data directory — Render Disk mounts here at /data
# NEXUS_DB_PATH is set at runtime to /data/nexus_memory.db
RUN mkdir -p /data && chown nexus:nexus /data

USER nexus

EXPOSE 8000

# Render injects $PORT. --workers 1 keeps SQLite WAL safe (single writer).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
