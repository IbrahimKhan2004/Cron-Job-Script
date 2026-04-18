# ─────────────────────────────────────────────
# Stage 1: Builder — installs deps with cache
# Changed: Multi-stage + BuildKit cache mount
# Why: pip install cached across builds — only
#      re-runs when requirements.txt changes
# ─────────────────────────────────────────────
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# Changed: System deps cached separately so they
# don't reinstall unless this layer changes
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Changed: Copy ONLY requirements first so pip
# layer is cached — app code changes won't
# invalidate this expensive step
COPY requirements.txt .

# Changed: --mount=type=cache keeps pip's HTTP
# cache on disk between builds (BuildKit feature)
# Result: 2nd+ builds skip downloading packages
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# ─────────────────────────────────────────────
# Stage 2: Runtime — lean final image
# Changed: Only copies installed packages +
#          app code, no build tools in final img
# Why: Smaller image = faster push/pull too
# ─────────────────────────────────────────────
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Changed: Copy pre-built site-packages from
# builder stage — no pip install in final stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Changed: App code copied last — most frequent
# change, so it's the last (cheapest) layer
COPY . .

EXPOSE 8080

RUN chmod +x start.sh

CMD ["./start.sh"]
