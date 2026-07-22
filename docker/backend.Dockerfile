FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1
WORKDIR /build

COPY backend/pyproject.toml /build/pyproject.toml
COPY backend/app /build/app
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install --no-install-recommends --yes gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system aiops \
    && useradd --system --gid aiops --home-dir /app aiops

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY backend/app /app/app
COPY backend/alembic.ini /app/alembic.ini
COPY backend/alembic /app/alembic
COPY scripts/seed_backend.py /app/scripts/seed_backend.py
COPY docker/backend-entrypoint.sh /usr/local/bin/aiops-entrypoint

RUN chmod 0555 /usr/local/bin/aiops-entrypoint \
    && mkdir -p /app/data \
    && chown -R aiops:aiops /app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=3)"

ENTRYPOINT ["aiops-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
