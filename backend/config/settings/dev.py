"""Development settings."""

from __future__ import annotations

from config.settings.base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# The Next.js storefront runs on :3000. Allow both hostnames a developer might
# use so the cookie-JWT flow works regardless of how the dev server is opened.
# (Browsers treat localhost and 127.0.0.1 as distinct origins.)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
