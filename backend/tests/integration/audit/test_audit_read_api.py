"""Integration tests for the audit read endpoint (full request path + DB).

Cover the secure-by-default posture (manage_access required), newest-first
ordering, the filters, the limit ceiling, and the response shape.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone
from rest_framework.test import APIClient

from src.domain.access.registry import ACCESS_ADMIN_ROLE
from src.infrastructure.access.gateway import GuardianAccessControl
from src.infrastructure.audit.models import AuditLogModel

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_URL = "/api/v1/audit/entries/"


def _user(phone: str) -> AbstractBaseUser:
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


@pytest.fixture
def admin_client() -> APIClient:
    user = _user("09120000001")
    # Assign the role straight through the gateway: setup must not itself write an
    # audit row, or it would pollute the listing under test.
    GuardianAccessControl().assign_role(user.pk, ACCESS_ADMIN_ROLE)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _row(action: str, *, resource_id: str = "1", seconds_ago: int = 0, **changes: object) -> None:
    AuditLogModel.objects.create(
        action=action,
        resource_type="channel",
        resource_id=resource_id,
        actor="42",
        changes=changes,
        occurred_at=timezone.now() - timedelta(seconds=seconds_ago),
    )


class TestAuthorization:
    def test_anonymous_is_rejected(self) -> None:
        assert APIClient().get(_URL).status_code == 401

    def test_a_non_admin_is_forbidden(self) -> None:
        client = APIClient()
        client.force_authenticate(user=_user("09120000002"))
        assert client.get(_URL).status_code == 403


class TestListing:
    def test_returns_entries_newest_first(self, admin_client: APIClient) -> None:
        _row("channel.created", seconds_ago=10)
        _row("channel.status_changed", seconds_ago=0)

        response = admin_client.get(_URL)

        assert response.status_code == 200
        assert [e["action"] for e in response.data] == [
            "channel.status_changed",
            "channel.created",
        ]

    def test_filters_by_action(self, admin_client: APIClient) -> None:
        _row("channel.created")
        _row("channel.status_changed")

        response = admin_client.get(_URL, {"action": "channel.created"})

        assert [e["action"] for e in response.data] == ["channel.created"]

    def test_filters_by_resource(self, admin_client: APIClient) -> None:
        _row("channel.created", resource_id="7")
        _row("channel.created", resource_id="8")

        response = admin_client.get(_URL, {"resource_type": "channel", "resource_id": "7"})

        assert [e["resource_id"] for e in response.data] == ["7"]

    def test_respects_the_limit(self, admin_client: APIClient) -> None:
        for i in range(3):
            _row("channel.created", seconds_ago=i)

        response = admin_client.get(_URL, {"limit": "2"})

        assert len(response.data) == 2

    def test_a_malformed_limit_falls_back_to_the_default(self, admin_client: APIClient) -> None:
        _row("channel.created")

        response = admin_client.get(_URL, {"limit": "not-a-number"})

        assert response.status_code == 200
        assert len(response.data) == 1

    def test_projects_the_full_entry_shape(self, admin_client: APIClient) -> None:
        _row("channel.status_changed", is_active={"before": True, "after": False})

        entry = admin_client.get(_URL).data[0]

        assert entry["actor"] == "42"
        assert entry["resource_type"] == "channel"
        assert "occurred_at" in entry
        assert entry["changes"] == {"is_active": {"before": True, "after": False}}
