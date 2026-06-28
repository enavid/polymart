"""Production settings."""
from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from config.settings.base import *  # noqa: F403
from config.settings.base import INSECURE_SECRET_KEY_SENTINEL, SECRET_KEY, env

DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# Fail fast (fail-closed): production must never run with the insecure dev key.
# base.py falls back to a well-known placeholder when DJANGO_SECRET_KEY is unset,
# which would silently ship a publicly known signing key.
if SECRET_KEY == INSECURE_SECRET_KEY_SENTINEL:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a unique, secret value in production; "
        "the insecure development default is not allowed."
    )

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
