"""Integration tests for the health endpoint (full request path + database)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from structlog.testing import capture_logs

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_health_endpoint_returns_200_and_healthy() -> None:
    client = APIClient()

    response = client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.data["state"] == "healthy"


def test_health_endpoint_reports_known_components() -> None:
    client = APIClient()

    response = client.get("/api/v1/health/")

    names = {component["name"] for component in response.data["components"]}
    assert {"application", "database"} <= names


def test_healthy_probe_logs_at_debug_to_avoid_probe_spam() -> None:
    # Liveness/readiness probes hit this endpoint constantly; a healthy result
    # must not flood the logs at INFO. It is logged at debug instead.
    client = APIClient()

    with capture_logs() as logs:
        client.get("/api/v1/health/")

    events = [entry for entry in logs if entry["event"] == "health_check"]
    assert events, "expected a health_check log event"
    assert events[0]["log_level"] == "debug"


def test_health_endpoint_echoes_request_id_header() -> None:
    client = APIClient()

    response = client.get("/api/v1/health/", HTTP_X_REQUEST_ID="abc-123")

    assert response.headers["X-Request-ID"] == "abc-123"
