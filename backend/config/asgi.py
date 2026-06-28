"""ASGI entry point."""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

from config.observability import configure_tracing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
configure_tracing()

application = get_asgi_application()
