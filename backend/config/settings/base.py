"""Base Django settings shared across environments."""
from __future__ import annotations

from pathlib import Path

import environ

from config.logging import build_logging_config, configure_structlog

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# --- Core -------------------------------------------------------------------
# Well-known placeholder used only for local dev/CI. prod.py rejects it so a
# missing DJANGO_SECRET_KEY can never silently ship a publicly known key.
INSECURE_SECRET_KEY_SENTINEL = "insecure-dev-key-change-me"  # nosec B105 - not a real secret; prod.py rejects this placeholder
SECRET_KEY = env("DJANGO_SECRET_KEY", default=INSECURE_SECRET_KEY_SENTINEL)
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "guardian",
    # Local bounded contexts (infrastructure adapters owning the ORM models).
    "src.infrastructure.channel.apps.ChannelConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.RequestIDMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

# --- Database / cache / broker ---------------------------------------------
# A full DATABASE_URL wins (prod/CI set it explicitly). Otherwise the connection
# is assembled from discrete POSTGRES_* parts so a single POSTGRES_PORT change in
# backend/.env drives both Django and the Docker port mapping (see Makefile).
if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env("POSTGRES_PORT", default="5432"),
            "NAME": env("POSTGRES_DB", default="polymart"),
            "USER": env("POSTGRES_USER", default="polymart"),
            "PASSWORD": env("POSTGRES_PASSWORD", default="polymart"),
        }
    }

REDIS_URL = env(
    "REDIS_URL",
    default="redis://{host}:{port}/0".format(
        host=env("REDIS_HOST", default="localhost"),
        port=env("REDIS_PORT", default="6379"),
    ),
)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    },
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_ACKS_LATE = True

# --- Auth -------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "guardian.backends.ObjectPermissionBackend",
]

# --- DRF (secure-by-default) ------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Polymart API",
    "DESCRIPTION": "White-label, multi-niche e-commerce platform API.",
    "VERSION": "0.0.1",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --- i18n / tz (Iran-first) -------------------------------------------------
LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Observability ----------------------------------------------------------
LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")
JSON_LOGS = env.bool("DJANGO_JSON_LOGS", default=not DEBUG)
configure_structlog()
LOGGING = build_logging_config(json_logs=JSON_LOGS, level=LOG_LEVEL)
