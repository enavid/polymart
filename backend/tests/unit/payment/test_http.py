"""Unit tests for the stdlib HTTP transport (urlopen patched -- no real network)."""

from __future__ import annotations

import io
from typing import Any

import pytest

from src.infrastructure.payment import http as http_module
from src.infrastructure.payment.http import HttpError, UrllibHttpTransport


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_post_json_returns_the_decoded_object(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int) -> _FakeResponse:
        seen["url"] = req.full_url
        seen["body"] = req.data
        return _FakeResponse(b'{"data": {"code": 100}}')

    monkeypatch.setattr(http_module.request, "urlopen", fake_urlopen)
    result = UrllibHttpTransport().post_json("https://gw/x", {"a": 1})

    assert result == {"data": {"code": 100}}
    assert seen["url"] == "https://gw/x"
    assert b'"a": 1' in seen["body"]


def test_post_json_rejects_a_non_https_url() -> None:
    with pytest.raises(HttpError):
        UrllibHttpTransport().post_json("http://gw/x", {})


def test_post_json_wraps_a_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(req: Any, timeout: int) -> None:
        raise TimeoutError("slow")

    monkeypatch.setattr(http_module.request, "urlopen", boom)
    with pytest.raises(HttpError):
        UrllibHttpTransport().post_json("https://gw/x", {})
