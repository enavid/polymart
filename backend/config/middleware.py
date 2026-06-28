"""Cross-cutting HTTP middleware."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import structlog
from django.http import HttpRequest, HttpResponse

REQUEST_ID_HEADER = "X-Request-ID"
_META_KEY = "HTTP_X_REQUEST_ID"


class RequestIDMiddleware:
    """Bind a correlation id to every request for logging and tracing.

    The id is taken from the incoming ``X-Request-ID`` header when present,
    otherwise a new one is generated. It is bound to the structlog context so
    every log line for the request is correlated, and echoed back on the
    response.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.META.get(_META_KEY) or uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = self.get_response(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response[REQUEST_ID_HEADER] = request_id
        return response
