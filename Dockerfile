# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip \
    && /opt/venv/bin/python -m pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    MODEL_OFFLINE_MODE=false

WORKDIR /app

RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup appuser \
    && mkdir -p /app/data /app/logs /app/traces \
    && chown -R appuser:appgroup /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup . .

USER appuser


FROM runtime-base AS cli

CMD ["python", "src/app.py"]


FROM runtime-base AS web

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "src/ui/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]