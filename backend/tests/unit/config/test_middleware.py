"""Unit tests for RequestIDMiddleware (request correlation)."""
from __future__ import annotations

import contextlib

import structlog
from django.http import HttpResponse
from django.test import RequestFactory

from config.middleware import REQUEST_ID_HEADER, RequestIDMiddleware


def test_generates_a_request_id_when_none_is_supplied() -> None:
    seen: dict[str, object] = {}

    def get_response(_request: object) -> HttpResponse:
        # Capture the bound context while the request is in flight.
        seen.update(structlog.contextvars.get_contextvars())
        return HttpResponse("ok")

    middleware = RequestIDMiddleware(get_response)
    request = RequestFactory().get("/")

    response = middleware(request)

    request_id = response[REQUEST_ID_HEADER]
    assert request_id
    assert seen["request_id"] == request_id
    assert request.request_id == request_id  # type: ignore[attr-defined]


def test_preserves_an_incoming_request_id() -> None:
    middleware = RequestIDMiddleware(lambda _request: HttpResponse("ok"))
    request = RequestFactory().get("/", HTTP_X_REQUEST_ID="given-id-123")

    response = middleware(request)

    assert response[REQUEST_ID_HEADER] == "given-id-123"


def test_clears_the_context_after_the_request() -> None:
    middleware = RequestIDMiddleware(lambda _request: HttpResponse("ok"))

    middleware(RequestFactory().get("/"))

    assert "request_id" not in structlog.contextvars.get_contextvars()


def test_clears_the_context_even_when_the_view_raises() -> None:
    def boom(_request: object) -> HttpResponse:
        raise ValueError("kaboom")

    middleware = RequestIDMiddleware(boom)

    with contextlib.suppress(ValueError):
        middleware(RequestFactory().get("/"))

    assert "request_id" not in structlog.contextvars.get_contextvars()
