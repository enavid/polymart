"""Test settings: fast and deterministic."""

from __future__ import annotations

from config.settings.base import *  # noqa: F403
from config.settings.base import env

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
# Tests use the offline mock online gateway (no live PSP), even though DEBUG is False here.
PAYMENT_ONLINE_MOCK = True

# Tests are hermetic: they never touch the dev/prod database from DATABASE_URL.
# Default to an isolated in-memory SQLite; CI sets TEST_DATABASE_URL to run the
# suite against PostgreSQL.
DATABASES = {
    "default": env.db("TEST_DATABASE_URL", default="sqlite://:memory:"),
}

# Use a local-memory cache so tests do not require a running Redis instance.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
