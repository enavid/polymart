"""Integration tests for the access-administration HTTP endpoints.

Cover the secure-by-default posture (auth + manage_access required), the happy
paths (role assignment and channel grant, each leaving an audit row), and the
mapping of unknown role/user/channel to HTTP status codes.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient

from src.domain.access.registry import ACCESS_ADMIN_ROLE, CHANNEL_ADMIN_ROLE
from src.infrastructure.access.gateway import GuardianAccessControl
from src.infrastructure.audit.models import AuditLogModel
from src.infrastructure.channel.models import ChannelModel
from src.interface.api.access.container import build_assign_role

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_ROLES_URL = "/api/v1/access/role-assignments/"
_GRANTS_URL = "/api/v1/access/channel-grants/"
_USERS_URL = "/api/v1/access/users/"


def _user(phone: str) -> AbstractBaseUser:
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


@pytest.fixture
def admin_user() -> AbstractBaseUser:
    """An access administrator (access_admin role -> manage_access)."""
    user = _user("09120000001")
    build_assign_role().execute(user_id=user.pk, role_name=ACCESS_ADMIN_ROLE)
    return user


@pytest.fixture
def admin_client(admin_user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


class TestAuthorization:
    def test_anonymous_is_rejected(self) -> None:
        response = APIClient().post(_ROLES_URL, {"user_id": 1, "role": "x"}, format="json")
        assert response.status_code == 401

    def test_a_non_admin_is_forbidden(self) -> None:
        client = APIClient()
        client.force_authenticate(user=_user("09120000002"))

        response = client.post(_ROLES_URL, {"user_id": 1, "role": "x"}, format="json")
        assert response.status_code == 403


class TestRoleAssignment:
    def test_admin_assigns_a_role_and_it_is_audited(self, admin_client: APIClient) -> None:
        target = _user("09120000003")

        response = admin_client.post(
            _ROLES_URL, {"user_id": target.pk, "role": CHANNEL_ADMIN_ROLE}, format="json"
        )

        assert response.status_code == 200
        assert target.groups.filter(name=CHANNEL_ADMIN_ROLE).exists()
        entry = AuditLogModel.objects.get(action="access.role_assigned", resource_id=str(target.pk))
        assert entry.changes == {"role": {"before": None, "after": CHANNEL_ADMIN_ROLE}}

    def test_an_unknown_role_is_a_400(self, admin_client: APIClient) -> None:
        target = _user("09120000004")

        response = admin_client.post(
            _ROLES_URL, {"user_id": target.pk, "role": "no_such_role"}, format="json"
        )
        assert response.status_code == 400

    def test_an_unknown_user_is_a_404(self, admin_client: APIClient) -> None:
        response = admin_client.post(
            _ROLES_URL, {"user_id": 999999, "role": CHANNEL_ADMIN_ROLE}, format="json"
        )
        assert response.status_code == 404


class TestChannelGrant:
    def test_admin_grants_scope_and_it_is_audited(self, admin_client: APIClient) -> None:
        target = _user("09120000005")
        channel = ChannelModel.objects.create(slug="coffee", name="Coffee", currency_code="IRR")

        response = admin_client.post(
            _GRANTS_URL, {"user_id": target.pk, "channel_slug": "coffee"}, format="json"
        )

        assert response.status_code == 200
        assert GuardianAccessControl().can_manage_channel(target.pk, channel.pk)
        entry = AuditLogModel.objects.get(
            action="access.channel_management_granted", resource_id=str(target.pk)
        )
        assert entry.changes == {"managed_channel": {"before": None, "after": "coffee"}}

    def test_an_unknown_channel_is_a_404(self, admin_client: APIClient) -> None:
        target = _user("09120000006")

        response = admin_client.post(
            _GRANTS_URL, {"user_id": target.pk, "channel_slug": "ghost"}, format="json"
        )
        assert response.status_code == 404

    def test_an_unknown_user_is_a_404(self, admin_client: APIClient) -> None:
        ChannelModel.objects.create(slug="coffee", name="Coffee", currency_code="IRR")

        response = admin_client.post(
            _GRANTS_URL, {"user_id": 999999, "channel_slug": "coffee"}, format="json"
        )
        assert response.status_code == 404


class TestUserAdminAuthorization:
    def test_anonymous_is_rejected(self) -> None:
        assert APIClient().get(_USERS_URL).status_code == 401

    def test_a_non_admin_is_forbidden(self) -> None:
        client = APIClient()
        client.force_authenticate(user=_user("09120000007"))

        assert client.get(_USERS_URL).status_code == 403


class TestUserList:
    def test_lists_accounts_with_the_total_count(self, admin_client: APIClient) -> None:
        # The admin fixture user plus two more.
        _user("09120000008")
        _user("09120000009")

        response = admin_client.get(_USERS_URL)

        assert response.status_code == 200
        assert response.data["count"] == 3
        assert {row["phone_number"] for row in response.data["results"]} >= {
            "+989120000008",
            "+989120000009",
        }
        # The list never carries a password field.
        assert all("password" not in row for row in response.data["results"])

    def test_pagination_windows_the_results(self, admin_client: APIClient) -> None:
        _user("09120000010")

        response = admin_client.get(_USERS_URL, {"limit": 1, "offset": 0})

        assert len(response.data["results"]) == 1
        assert response.data["count"] == 2
        assert response.data["limit"] == 1
        assert response.data["offset"] == 0

    def test_an_out_of_range_limit_is_a_400(self, admin_client: APIClient) -> None:
        assert admin_client.get(_USERS_URL, {"limit": 1000}).status_code == 400


class TestUserCreate:
    def test_admin_creates_a_user_and_it_is_audited(self, admin_client: APIClient) -> None:
        response = admin_client.post(
            _USERS_URL,
            {
                "phone_number": "09121112233",
                "password": "pw",
                "full_name": "Sara",
                "is_staff": True,
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["full_name"] == "Sara"
        assert response.data["is_staff"] is True
        assert response.data["phone_number"] == "+989121112233"
        # The password is write-only; it must never be echoed back.
        assert "password" not in response.data
        created = get_user_model().objects.get(phone_number="+989121112233")
        assert AuditLogModel.objects.filter(
            action="user.created", resource_id=str(created.pk)
        ).exists()

    def test_the_created_user_can_authenticate_with_the_password(
        self, admin_client: APIClient
    ) -> None:
        admin_client.post(
            _USERS_URL,
            {"phone_number": "09121112244", "password": "s3cret-pw"},
            format="json",
        )

        login = APIClient().post(
            "/api/v1/auth/login/",
            {"phone_number": "09121112244", "password": "s3cret-pw"},
            format="json",
        )
        assert login.status_code == 200

    def test_a_duplicate_phone_is_a_409(self, admin_client: APIClient) -> None:
        payload = {"phone_number": "09121112255", "password": "pw"}
        assert admin_client.post(_USERS_URL, payload, format="json").status_code == 201

        assert admin_client.post(_USERS_URL, payload, format="json").status_code == 409

    def test_an_invalid_phone_is_a_400(self, admin_client: APIClient) -> None:
        response = admin_client.post(
            _USERS_URL, {"phone_number": "not-a-phone", "password": "pw"}, format="json"
        )
        assert response.status_code == 400

    def test_a_non_admin_cannot_create(self) -> None:
        client = APIClient()
        client.force_authenticate(user=_user("09120000011"))

        response = client.post(
            _USERS_URL, {"phone_number": "09121112266", "password": "pw"}, format="json"
        )
        assert response.status_code == 403
