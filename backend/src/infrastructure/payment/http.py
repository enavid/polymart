"""A tiny JSON-over-HTTP transport, behind a port so gateway adapters stay testable.

An online gateway adapter (Zarinpal, ...) calls the provider's REST API. Depending on a
narrow ``HttpTransport`` port -- rather than importing a client directly -- keeps the
adapter unit-testable against a fake transport (no live network), and keeps the choice of
HTTP client an infrastructure detail. The default adapter uses the standard library, so no
new dependency is pulled in for a rarely-exercised prod path.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any
from urllib import error, request

_DEFAULT_TIMEOUT_SECONDS = 15


class HttpError(Exception):
    """Raised when an HTTP call fails at the transport level (network/decode/status)."""


class HttpTransport(ABC):
    """Narrow boundary for a JSON POST, injected into gateway adapters."""

    @abstractmethod
    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST ``payload`` as JSON and return the decoded JSON response object."""


class UrllibHttpTransport(HttpTransport):
    """Standard-library JSON POST. No third-party dependency."""

    def __init__(self, *, timeout: int = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        # The url is a fixed, configured gateway endpoint (never user input); require https
        # so a misconfiguration can never downgrade to a file:/http: scheme.
        if not url.startswith("https://"):
            raise HttpError(f"gateway url must be https: {url!r}")
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self._timeout) as response:  # nosec B310 - https-only, configured gateway url
                decoded = json.loads(response.read().decode("utf-8"))
        except (error.URLError, ValueError, TimeoutError) as exc:
            raise HttpError(f"gateway request failed: {exc}") from exc
        if not isinstance(decoded, dict):  # pragma: no cover - defensive
            raise HttpError("gateway response was not a JSON object")
        return decoded
