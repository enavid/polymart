"""WSGI entry point."""

from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

from config.observability import configure_tracing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
configure_tracing()

application = get_wsgi_application()
