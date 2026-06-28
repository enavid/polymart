"""Unit tests for the channel DRF permission classes (no Django, no database).

These guard security-critical decisions, so they are tested directly against
lightweight fakes -- not only through the endpoints -- to pin every branch.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.domain.channel.entities import Channel
from src.domain.channel.value_objects import ChannelSlug, Currency
from src.interface.api.access import permissions as perms
from src.interface.api.access.permissions import (
    GlobalChannelManagePermission,
    ScopedChannelManagePermission,
)


@dataclass
class FakeUser:
    authenticated: bool = True
    pk: int = 1
    granted: bool = False

    @property
    def is_authenticated(self) -> bool:
        return self.authenticated

    def has_perm(self, codename: str) -> bool:
        return self.granted


@dataclass
class FakeRequest:
    method: str
    user: FakeUser


def _channel(channel_id: int = 42) -> Channel:
    return Channel(
        slug=ChannelSlug("coffee"), name="Coffee", currency=Currency("IRR"), id=channel_id
    )


class TestGlobalChannelManagePermission:
    def test_rejects_an_unauthenticated_request(self) -> None:
        request = FakeRequest("GET", FakeUser(authenticated=False))

        assert GlobalChannelManagePermission().has_permission(request, None) is False

    def test_allows_authenticated_reads(self) -> None:
        request = FakeRequest("GET", FakeUser(granted=False))

        assert GlobalChannelManagePermission().has_permission(request, None) is True

    def test_allows_writes_only_with_the_global_permission(self) -> None:
        with_perm = FakeRequest("POST", FakeUser(granted=True))
        without_perm = FakeRequest("POST", FakeUser(granted=False))

        assert GlobalChannelManagePermission().has_permission(with_perm, None) is True
        assert GlobalChannelManagePermission().has_permission(without_perm, None) is False


class TestScopedChannelManagePermission:
    def test_has_permission_only_checks_authentication(self) -> None:
        assert (
            ScopedChannelManagePermission().has_permission(
                FakeRequest("PATCH", FakeUser(granted=False)), None
            )
            is True
        )
        assert (
            ScopedChannelManagePermission().has_permission(
                FakeRequest("PATCH", FakeUser(authenticated=False)), None
            )
            is False
        )

    def test_object_permission_allows_safe_methods_without_a_grant(self) -> None:
        request = FakeRequest("GET", FakeUser(granted=False))

        result = ScopedChannelManagePermission().has_object_permission(request, None, _channel())

        assert result is True

    @pytest.mark.parametrize("can_manage", [True, False])
    def test_object_permission_for_writes_delegates_to_the_gateway(
        self, monkeypatch: pytest.MonkeyPatch, can_manage: bool
    ) -> None:
        seen: dict[str, object] = {}

        class FakeGateway:
            def can_manage_channel(self, user_id: int, channel_id: int) -> bool:
                seen["args"] = (user_id, channel_id)
                return can_manage

        monkeypatch.setattr(perms, "build_access_gateway", FakeGateway)
        request = FakeRequest("PATCH", FakeUser(pk=7))

        result = ScopedChannelManagePermission().has_object_permission(request, None, _channel(42))

        assert result is can_manage
        assert seen["args"] == (7, 42)
