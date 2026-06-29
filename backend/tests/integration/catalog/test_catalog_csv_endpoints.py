"""Integration tests for the catalog CSV export/import endpoints (full path + DB)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from src.application.catalog import use_cases
from src.domain.access.registry import CATALOG_ADMIN_ROLE
from src.interface.api.access.container import build_assign_role
from src.interface.api.catalog import views

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_EXPORT_URL = "/api/v1/catalog/products/export/"
_IMPORT_URL = "/api/v1/catalog/products/import/"


@pytest.fixture
def admin_user() -> AbstractBaseUser:
    user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
    build_assign_role().execute(user_id=user.pk, role_name=CATALOG_ADMIN_ROLE)
    return user


@pytest.fixture
def auth_client(admin_user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def member_client() -> APIClient:
    user = get_user_model().objects.create_user(phone_number="09120000002", password="pw")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _seed_type(client: APIClient) -> None:
    assert (
        client.post(
            "/api/v1/catalog/product-types/",
            {"code": "coffee", "name": "Coffee"},
            format="json",
        ).status_code
        == 201
    )


def _upload(text: str) -> SimpleUploadedFile:
    return SimpleUploadedFile("products.csv", text.encode("utf-8"), content_type="text/csv")


class TestExportSecurity:
    def test_requires_authentication(self) -> None:
        assert APIClient().get(_EXPORT_URL).status_code == 401

    def test_any_authenticated_user_can_export(self, member_client: APIClient) -> None:
        # Export is a read: it follows the catalog read posture (the same data is
        # already reachable through the management product reads), so an authenticated
        # member is allowed. The write side (import) is what needs the manage perm.
        assert member_client.get(_EXPORT_URL).status_code == 200


class TestExport:
    def test_returns_a_csv_attachment_of_products(self, auth_client: APIClient) -> None:
        _seed_type(auth_client)
        auth_client.post(
            "/api/v1/catalog/products/",
            {"code": "house-blend", "name": "House Blend", "product_type": "coffee"},
            format="json",
        )

        response = auth_client.get(_EXPORT_URL)

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert "attachment" in response["Content-Disposition"]
        body = response.content.decode("utf-8")
        assert body.splitlines()[0].startswith("code,name,product_type,is_published,categories")
        assert "house-blend" in body


class TestImportSecurity:
    def test_requires_authentication(self) -> None:
        response = APIClient().post(
            _IMPORT_URL, {"file": _upload("code,name,product_type\n")}, format="multipart"
        )
        assert response.status_code == 401

    def test_member_without_permission_is_forbidden(self, member_client: APIClient) -> None:
        response = member_client.post(
            _IMPORT_URL, {"file": _upload("code,name,product_type\n")}, format="multipart"
        )
        assert response.status_code == 403


class TestImport:
    def test_imports_products_creating_them(self, auth_client: APIClient) -> None:
        _seed_type(auth_client)
        csv_text = "code,name,product_type\nhouse-blend,House Blend,coffee\n"

        response = auth_client.post(_IMPORT_URL, {"file": _upload(csv_text)}, format="multipart")

        assert response.status_code == 200
        assert response.data["created"] == 1
        assert response.data["errors"] == []
        assert auth_client.get("/api/v1/catalog/products/house-blend/").status_code == 200

    def test_round_trips_an_exported_file(self, auth_client: APIClient) -> None:
        _seed_type(auth_client)
        auth_client.post(
            "/api/v1/catalog/products/",
            {"code": "house-blend", "name": "House Blend", "product_type": "coffee"},
            format="json",
        )
        exported = auth_client.get(_EXPORT_URL).content.decode("utf-8")
        # Re-importing the same products must fail every row as already-existing
        # (the export is faithful enough to be recognised on the way back in).
        response = auth_client.post(_IMPORT_URL, {"file": _upload(exported)}, format="multipart")

        assert response.status_code == 400
        assert "already exists" in response.data["errors"][0]["error"]

    def test_reports_row_errors_and_writes_nothing(self, auth_client: APIClient) -> None:
        _seed_type(auth_client)
        csv_text = (
            "code,name,product_type\n"
            "house-blend,House Blend,coffee\n"
            "ghost,Ghost,missing-type\n"
        )

        response = auth_client.post(_IMPORT_URL, {"file": _upload(csv_text)}, format="multipart")

        assert response.status_code == 400
        assert response.data["created"] == 0
        assert response.data["errors"][0]["row_number"] == 2
        assert auth_client.get("/api/v1/catalog/products/house-blend/").status_code == 404

    def test_a_missing_required_column_is_rejected(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            _IMPORT_URL, {"file": _upload("code,name\nx,X\n")}, format="multipart"
        )

        assert response.status_code == 400

    def test_a_missing_file_is_rejected(self, auth_client: APIClient) -> None:
        assert auth_client.post(_IMPORT_URL, {}, format="multipart").status_code == 400

    def test_an_oversized_file_is_rejected(
        self, auth_client: APIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(views, "_MAX_IMPORT_BYTES", 5)

        response = auth_client.post(
            _IMPORT_URL,
            {"file": _upload("code,name,product_type\n")},
            format="multipart",
        )

        assert response.status_code == 400
        assert "exceeds" in response.data["errors"][0]["error"]

    def test_too_many_rows_is_rejected(
        self, auth_client: APIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed_type(auth_client)
        monkeypatch.setattr(use_cases, "_MAX_IMPORT_ROWS", 1)
        csv_text = "code,name,product_type\na,A,coffee\nb,B,coffee\n"

        response = auth_client.post(_IMPORT_URL, {"file": _upload(csv_text)}, format="multipart")

        assert response.status_code == 400
        assert response.data["errors"][0]["row_number"] == 0
        assert "too large" in response.data["errors"][0]["error"]

    def test_a_non_utf8_file_is_rejected(self, auth_client: APIClient) -> None:
        upload = SimpleUploadedFile("p.csv", b"\xff\xfe\x00", content_type="text/csv")
        response = auth_client.post(_IMPORT_URL, {"file": upload}, format="multipart")
        assert response.status_code == 400

    def test_audit_log_records_the_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        _seed_type(auth_client)
        csv_text = "code,name,product_type\nhouse-blend,House Blend,coffee\n"
        with capture_logs() as logs:
            auth_client.post(_IMPORT_URL, {"file": _upload(csv_text)}, format="multipart")

        events = [e for e in logs if e["event"] == "catalog_products_imported"]
        assert events and events[0]["actor"] == str(admin_user.pk)
