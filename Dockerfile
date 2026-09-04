ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-alpine AS python-deps

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apk add --no-cache --virtual .build-deps \
        build-base \
        linux-headers

COPY requirements-runtime.txt .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements-runtime.txt \
    && find /opt/venv -type d -name __pycache__ -prune -exec rm -rf {} + \
    && find /opt/venv -type f -name "*.pyc" -delete \
    && find /opt/venv -type f -name "*.pyo" -delete \
    && find /opt/venv -type d -name "tests" -prune -exec rm -rf {} + \
    && rm -rf /opt/venv/bin/pip* \
        /opt/venv/lib/python*/site-packages/pip* \
        /opt/venv/lib/python*/site-packages/wheel*

FROM python:${PYTHON_VERSION}-alpine AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    XDG_CACHE_HOME=/tmp/.cache \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000

WORKDIR /app

RUN addgroup -g "${APP_GID}" -S app \
    && adduser -u "${APP_UID}" -S -D -H -G app app \
    && mkdir -p /app /tmp/.cache \
    && chown -R app:app /app /tmp/.cache \
    && rm -rf /usr/local/bin/pip* \
        /usr/local/lib/python*/site-packages/pip* \
        /usr/local/lib/python*/site-packages/pkg_resources* \
        /usr/local/lib/python*/site-packages/setuptools* \
        /usr/local/lib/python*/site-packages/wheel* \
        /usr/local/lib/python*/site-packages/jaraco*

COPY --from=python-deps /opt/venv /opt/venv
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini main.py ./

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"UVICORN_PORT\", \"8000\")}/health', timeout=2).read()" || exit 1

CMD ["sh", "-c", "uvicorn main:app --host ${UVICORN_HOST} --port ${UVICORN_PORT}"]
