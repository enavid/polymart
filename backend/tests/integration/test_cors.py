"""Integration tests for cross-origin resource sharing (CORS).

The Next.js storefront runs on a different origin than the API in every
environment (different port locally, different host in prod), so the browser
issues cross-origin requests. Cookie-JWT auth additionally requires credentialed
CORS. These tests pin the contract: allowed origins are echoed back with
credentials enabled, and unknown origins are never granted access.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ALLOWED_ORIGIN = "http://localhost:3000"
UNKNOWN_ORIGIN = "http://evil.example.com"


@override_settings(CORS_ALLOWED_ORIGINS=[ALLOWED_ORIGIN])
def test_allowed_origin_is_echoed_with_credentials() -> None:
    client = APIClient()

    response = client.get("/api/v1/health/", HTTP_ORIGIN=ALLOWED_ORIGIN)

    assert response["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert response["Access-Control-Allow-Credentials"] == "true"


@override_settings(CORS_ALLOWED_ORIGINS=[ALLOWED_ORIGIN])
def test_preflight_request_is_answered_for_an_allowed_origin() -> None:
    client = APIClient()

    response = client.options(
        "/api/v1/auth/login/",
        HTTP_ORIGIN=ALLOWED_ORIGIN,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
    )

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert response["Access-Control-Allow-Credentials"] == "true"


@override_settings(CORS_ALLOWED_ORIGINS=[ALLOWED_ORIGIN])
def test_unknown_origin_is_not_granted_access() -> None:
    client = APIClient()

    response = client.get("/api/v1/health/", HTTP_ORIGIN=UNKNOWN_ORIGIN)

    assert "Access-Control-Allow-Origin" not in response
