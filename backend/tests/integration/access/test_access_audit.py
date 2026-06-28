"""RBAC mutations leave a durable audit trail (real composition root).

Drives the access use cases through their real factories -- guardian gateway,
persistent recorder, Django audit trail -- to prove that assigning a role and
granting per-channel scope each write an ``audit_log`` row naming the subject
user, what changed, and who acted.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from src.domain.access.registry import CHANNEL_ADMIN_ROLE
from src.infrastructure.audit.models import AuditLogModel
from src.infrastructure.channel.models import ChannelModel
from src.interface.api.access.container import (
    build_assign_role,
    build_grant_channel_management,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _make_user(phone: str = "09120000009") -> int:
    return get_user_model().objects.create_user(phone_number=phone, password="pw").pk


class TestRoleAssignmentAudit:
    def test_assigning_a_role_writes_an_audit_row(self) -> None:
        user_id = _make_user()

        build_assign_role().execute(user_id=user_id, role_name=CHANNEL_ADMIN_ROLE, actor="42")

        entry = AuditLogModel.objects.get(action="access.role_assigned")
        assert entry.resource_type == "user"
        assert entry.resource_id == str(user_id)
        assert entry.actor == "42"
        assert entry.changes == {"role": {"before": None, "after": CHANNEL_ADMIN_ROLE}}


class TestChannelGrantAudit:
    def test_granting_channel_scope_writes_an_audit_row(self) -> None:
        user_id = _make_user()
        ChannelModel.objects.create(slug="coffee", name="Coffee", currency_code="IRR")

        build_grant_channel_management().execute(user_id=user_id, channel_slug="coffee", actor="42")

        entry = AuditLogModel.objects.get(action="access.channel_management_granted")
        assert entry.resource_id == str(user_id)
        assert entry.changes == {"managed_channel": {"before": None, "after": "coffee"}}
