"""Base Django settings shared across environments."""

from __future__ import annotations

from datetime import timedelta
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
    "corsheaders",
    "guardian",
    # Tracks issued refresh tokens so they can be revoked (logout, password reset).
    "rest_framework_simplejwt.token_blacklist",
    # Local bounded contexts (infrastructure adapters owning the ORM models).
    "src.infrastructure.identity.apps.IdentityConfig",
    "src.infrastructure.channel.apps.ChannelConfig",
    "src.infrastructure.access.apps.AccessConfig",
    "src.infrastructure.audit.apps.AuditConfig",
    "src.infrastructure.catalog.apps.CatalogConfig",
    "src.infrastructure.cart.apps.CartConfig",
    "src.infrastructure.order.apps.OrderConfig",
    "src.infrastructure.address.apps.AddressConfig",
    "src.infrastructure.payment.apps.PaymentConfig",
    "src.infrastructure.wallet.apps.WalletConfig",
    # Developer/E2E tooling (the seed_e2e management command). It carries no
    # models; its one command refuses to run unless DEBUG, so it is inert in
    # production even though it is installed everywhere.
    "src.infrastructure.devtools.apps.DevtoolsConfig",
]

# Phone-first custom user (see src/infrastructure/identity/models.py).
AUTH_USER_MODEL = "identity.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # CorsMiddleware must sit above CommonMiddleware so it can answer preflight
    # OPTIONS requests and attach the Access-Control-* headers to every response.
    "corsheaders.middleware.CorsMiddleware",
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

# --- Payments (online gateway) ----------------------------------------------
# Use the offline mock online gateway (no real PSP) by default in dev/test; production
# (DEBUG=False) wires the real Zarinpal adapter. Mirrors the OTP dev-sender guard.
PAYMENT_ONLINE_MOCK = env.bool("PAYMENT_ONLINE_MOCK", default=DEBUG)
# The browser is sent here for the mock gateway page, and a gateway redirects back here (the
# callback). Relative paths resolve against the storefront origin, which proxies /api to the
# backend; production sets an absolute callback URL the PSP can reach.
PAYMENT_MOCK_GATEWAY_URL = env("PAYMENT_MOCK_GATEWAY_URL", default="/api/v1/payments/mock-gateway/")
PAYMENT_CALLBACK_URL = env("PAYMENT_CALLBACK_URL", default="/api/v1/payments/callback/")
# After the callback settles a payment, the browser is redirected to this storefront path
# with the order number appended, to show the result.
PAYMENT_RESULT_URL = env("PAYMENT_RESULT_URL", default="/orders")
# Zarinpal (the real online gateway, production).
ZARINPAL_MERCHANT_ID = env("ZARINPAL_MERCHANT_ID", default="")
ZARINPAL_SANDBOX = env.bool("ZARINPAL_SANDBOX", default=True)
# --- Payments (card-to-card) ------------------------------------------------
# The merchant's receiving card per channel, shown to a buyer who pays by manual bank
# transfer. Sensitive banking config, so it lives here with the other gateway settings (not a
# public model/API), keyed by channel slug so each channel collects on its own card:
#   PAYMENT_CARD_TO_CARD = {"ir-main": {"number": "6037-9911-1234-5678", "holder": "..."}}
# Empty by default; dev/test/E2E settings provide a deterministic value for ``ir-main``.
PAYMENT_CARD_TO_CARD = env.json("PAYMENT_CARD_TO_CARD", default={})

# --- Wallet -----------------------------------------------------------------
# The currency an empty (never-credited) wallet reports. Iran-first, so Rial by default; a
# wallet's real currency is fixed by its first credit (the refunded payment's currency).
WALLET_DEFAULT_CURRENCY = env("WALLET_DEFAULT_CURRENCY", default="IRR")

# --- Shipping (flat-rate) ---------------------------------------------------
# The delivery methods each channel offers, keyed by channel slug. Flat-rate config in this
# slice (a later slice moves rates to an admin model behind the same port), so it lives here
# like the other per-channel commerce settings. Each entry is a method:
#   SHIPPING_METHODS = {"ir-main": [
#       {"code": "standard", "name": "Standard post", "price": "50000",
#        "currency": "IRR", "min_days": 3, "max_days": 5}, ...]}
# The price is a string so the exact Decimal survives; currency is per-method (it must match
# the channel currency to be quotable at checkout). A method may carry an optional
# ``zone_rates`` map (zone code -> price) overriding the default price for that zone. Empty by
# default; dev/test/E2E provide a deterministic set for ``ir-main``.
SHIPPING_METHODS = env.json("SHIPPING_METHODS", default={})

# The shipping zones each channel defines, keyed by channel slug. A zone groups provinces
# that share a rate; a method's ``zone_rates`` override is keyed by a zone's ``code``. A
# destination's province is matched to a zone case/whitespace-insensitively; a province in no
# zone falls back to each method's default price.
#   SHIPPING_ZONES = {"ir-main": [
#       {"code": "tehran", "name": "تهران", "provinces": ["تهران"]}, ...]}
# Empty by default (no zones -> every destination pays the default rate).
SHIPPING_ZONES = env.json("SHIPPING_ZONES", default={})

# --- Tax (per-channel VAT rate) ---------------------------------------------
# The tax (value-added) rate each channel levies, keyed by channel slug. The value is the
# percentage as a string (so the exact Decimal survives), e.g. "9" for 9% VAT. Tax config in
# this slice (a later slice moves rates to an admin model, and tax classes/zones plug in,
# behind the same port), so it lives here like the other per-channel commerce settings:
#   TAX_RATES = {"ir-main": "9"}
# A channel absent from the map (or a malformed value) levies no tax. Empty by default;
# dev/test/E2E provide a deterministic rate for ``ir-main``.
TAX_RATES = env.json("TAX_RATES", default={})

# --- Auth -------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "guardian.backends.ObjectPermissionBackend",
]

# The API is authenticated-only (anonymous requests get 401 before any object
# check), so guardian's database-backed anonymous user is unnecessary -- and it
# would not fit our phone-first custom user. Disabling it avoids creating a
# synthetic "AnonymousUser" account at migrate time.
ANONYMOUS_USER_NAME = None

# --- DRF (secure-by-default) ------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Tokens are carried in HttpOnly cookies, not the Authorization header,
        # so JavaScript cannot read them (XSS-resistant). See identity slice.
        "src.interface.api.identity.authentication.CookieJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# --- JWT auth (tokens delivered as HttpOnly cookies) ------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# Cookie attributes for the access/refresh tokens. Secure is forced off only in
# DEBUG so local HTTP works; production (DEBUG=False) always sets Secure. The
# tokens are HttpOnly (no JS access) and SameSite=Lax (CSRF-resistant for the
# top-level navigations a storefront performs).
AUTH_COOKIE_ACCESS = "access_token"
AUTH_COOKIE_REFRESH = "refresh_token"
AUTH_COOKIE_SECURE = not DEBUG
AUTH_COOKIE_HTTPONLY = True
AUTH_COOKIE_SAMESITE = "Lax"
AUTH_COOKIE_PATH = "/"

# Guest (anonymous) session cookie. A shopper who has not signed in still needs a
# stable, unforgeable owner for their cart/order; the backend mints an opaque
# CSPRNG token into this HttpOnly cookie on their first cart write. It reuses the
# same Secure/SameSite/Path posture as the auth cookies -- the token is the
# credential, so it must never be readable by JS and must ride only same-site
# navigations. Thirty days is long enough to survive a return visit without
# becoming a de-facto permanent identifier.
GUEST_COOKIE_NAME = "guest_session"
GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 30

# --- CORS -------------------------------------------------------------------
# The storefront is always a different origin than the API (different port in
# local dev, different host in prod), so the browser makes cross-origin requests.
# Cookie-JWT auth means those requests are credentialed, which requires an
# explicit per-origin allow-list (wildcards are forbidden with credentials).
# Secure-by-default: no origins are allowed unless an environment opts in.
# dev.py whitelists localhost; prod reads CORS_ALLOWED_ORIGINS from the env.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

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
