"""Integration tests for the health endpoint (full request path + database)."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

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


def test_health_endpoint_echoes_request_id_header() -> None:
    client = APIClient()

    response = client.get("/api/v1/health/", HTTP_X_REQUEST_ID="abc-123")

    assert response.headers["X-Request-ID"] == "abc-123"
