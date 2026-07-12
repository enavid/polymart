"""Development settings."""

from __future__ import annotations

from config.settings.base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Run Celery tasks inline (no separate worker needed for local dev / the E2E harness), so a
# gateway callback settles the payment synchronously and the result is visible immediately.
# Production runs a real worker (eager off) for genuinely async processing.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# A deterministic card-to-card destination for the default channel, so the card-to-card flow
# (and the E2E harness) shows a known receiving card in local dev.
PAYMENT_CARD_TO_CARD = {
    "ir-main": {"number": "6037-9911-1234-5678", "holder": "Polymart Store"},
}

# Deterministic flat-rate shipping methods for the default channel, so the checkout chooser
# (and the E2E harness) shows a known set of methods and prices in local dev.
SHIPPING_METHODS = {
    "ir-main": [
        {
            "code": "standard",
            "name": "پست پیشتاز",
            "price": "50000",
            "currency": "IRR",
            "min_days": 3,
            "max_days": 5,
            "zone_rates": {"tehran": "30000"},
        },
        {
            "code": "express",
            "name": "پیک اکسپرس",
            "price": "120000",
            "currency": "IRR",
            "min_days": 1,
            "max_days": 2,
            "zone_rates": {"tehran": "90000"},
        },
        {
            "code": "free",
            "name": "ارسال رایگان",
            "price": "0",
            "currency": "IRR",
            "min_days": 5,
            "max_days": 7,
        },
        {
            "code": "pickup",
            "name": "تحویل حضوری",
            "price": "0",
            "currency": "IRR",
            "min_days": 0,
            "max_days": 1,
            "pickup": True,
        },
    ],
}

# Tehran is a discounted shipping zone (cheaper standard/express); every other province pays
# the default rate. Keyed by channel slug, matched on the address province.
SHIPPING_ZONES = {
    "ir-main": [{"code": "tehran", "name": "تهران", "provinces": ["تهران"]}],
}

# Iran levies a 9% value-added tax; the default channel charges it so the checkout/order
# breakdown and the E2E harness show a known tax on every placed order (goods + shipping).
TAX_RATES = {"ir-main": "9"}

# The Next.js storefront runs on :3000. Allow both hostnames a developer might
# use so the cookie-JWT flow works regardless of how the dev server is opened.
# (Browsers treat localhost and 127.0.0.1 as distinct origins.)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
