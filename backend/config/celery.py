"""Celery application entry point."""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("polymart")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
