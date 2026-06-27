# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/venv/bin:$PATH"
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /venv \
    && pip install --upgrade pip

# --- Development image: editable install with dev + observability extras -----
FROM base AS dev
COPY . .
RUN pip install -e ".[dev,observability]"
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# --- Production runtime image: non-root, gunicorn ----------------------------
FROM base AS runtime
COPY . .
RUN pip install ".[observability]" \
    && useradd --create-home app \
    && chown -R app:app /app /venv
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
