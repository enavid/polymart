"""End-to-end audit wiring: channel mutations leave a durable trail.

Drives the real HTTP path (and thus the real composition root: Django repository
-> persistent recorder -> Django audit trail) to prove that creating a channel
and changing its status each write an ``audit_log`` row with the acting user and
the before/after values.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient

from src.application.access.use_cases import AssignRole
from src.domain.access.registry import CHANNEL_ADMIN_ROLE
from src.infrastructure.access.gateway import GuardianAccessControl
from src.infrastructure.audit.models import AuditLogModel

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def admin_user() -> AbstractBaseUser:
    user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
    AssignRole(GuardianAccessControl()).execute(user_id=user.pk, role_name=CHANNEL_ADMIN_ROLE)
    return user


@pytest.fixture
def auth_client(admin_user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


def _create_coffee(client: APIClient) -> None:
    client.post(
        "/api/v1/channels/",
        {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
        format="json",
    )


class TestChannelAuditTrail:
    def test_creating_a_channel_is_audited_with_the_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        _create_coffee(auth_client)

        entry = AuditLogModel.objects.get(action="channel.created")
        # The trail records the stable user id, never the phone number (PII).
        assert entry.actor == str(admin_user.pk)
        assert entry.resource_type == "channel"
        assert entry.changes["is_active"]["after"] is True

    def test_status_change_is_audited_with_before_and_after(self, auth_client: APIClient) -> None:
        _create_coffee(auth_client)

        auth_client.patch("/api/v1/channels/coffee/", {"is_active": False}, format="json")

        entry = AuditLogModel.objects.get(action="channel.status_changed")
        assert entry.changes == {"is_active": {"before": True, "after": False}}

    def test_a_no_op_status_change_writes_no_audit_row(self, auth_client: APIClient) -> None:
        # The channel is already active; re-activating changes nothing, so there is
        # nothing to audit.
        _create_coffee(auth_client)

        auth_client.patch("/api/v1/channels/coffee/", {"is_active": True}, format="json")

        assert not AuditLogModel.objects.filter(action="channel.status_changed").exists()
