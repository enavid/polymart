"""Integration tests for the address-book HTTP endpoints (real stack).

Cover the secure-by-default posture (auth required), CRUD, the owner-scoping that
makes IDOR impossible, boundary/invalid input (400), the per-owner cap (409), and
default-address exclusivity end to end through the API.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_ADDRESSES_URL = "/api/v1/addresses/"

_VALID_BODY = {
    "recipient_name": "Sara Ahmadi",
    "phone_number": "09123456789",
    "province": "Tehran",
    "city": "Tehran",
    "postal_code": "1234567890",
    "line1": "Valiasr St, No. 1",
}


def _user(phone: str) -> AbstractBaseUser:
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


def _client(user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestAuthorization:
    def test_anonymous_cannot_list_addresses(self) -> None:
        assert APIClient().get(_ADDRESSES_URL).status_code == 401

    def test_anonymous_cannot_create_an_address(self) -> None:
        response = APIClient().post(_ADDRESSES_URL, _VALID_BODY, format="json")
        assert response.status_code == 401


class TestCreateAddress:
    def test_creates_an_address_and_returns_201(self) -> None:
        user = _user("09120000001")

        response = _client(user).post(_ADDRESSES_URL, _VALID_BODY, format="json")

        assert response.status_code == 201
        assert response.data["recipient_name"] == "Sara Ahmadi"
        assert response.data["phone_number"] == "+989123456789"
        assert response.data["id"].startswith("ADDR-")
        assert response.data["line2"] is None

    def test_the_first_address_is_the_default(self) -> None:
        user = _user("09120000001")

        response = _client(user).post(_ADDRESSES_URL, _VALID_BODY, format="json")

        assert response.data["is_default"] is True

    def test_a_second_address_is_not_default_by_default(self) -> None:
        client = _client(_user("09120000001"))
        client.post(_ADDRESSES_URL, _VALID_BODY, format="json")

        response = client.post(_ADDRESSES_URL, {**_VALID_BODY, "city": "Shiraz"}, format="json")

        assert response.data["is_default"] is False

    def test_an_invalid_postal_code_is_a_400(self) -> None:
        user = _user("09120000001")

        response = _client(user).post(
            _ADDRESSES_URL, {**_VALID_BODY, "postal_code": "123"}, format="json"
        )

        assert response.status_code == 400

    def test_an_invalid_phone_number_is_a_400(self) -> None:
        user = _user("09120000001")

        response = _client(user).post(
            _ADDRESSES_URL, {**_VALID_BODY, "phone_number": "0812345"}, format="json"
        )

        assert response.status_code == 400

    def test_a_blank_recipient_name_is_a_400(self) -> None:
        user = _user("09120000001")

        response = _client(user).post(
            _ADDRESSES_URL, {**_VALID_BODY, "recipient_name": "   "}, format="json"
        )

        assert response.status_code == 400

    def test_beyond_the_cap_is_a_409(self) -> None:
        client = _client(_user("09120000001"))
        for i in range(20):
            response = client.post(
                _ADDRESSES_URL, {**_VALID_BODY, "city": f"City{i}"}, format="json"
            )
            assert response.status_code == 201

        response = client.post(
            _ADDRESSES_URL, {**_VALID_BODY, "city": "One too many"}, format="json"
        )

        assert response.status_code == 409


class TestListAddresses:
    def test_lists_only_the_callers_addresses(self) -> None:
        alice = _user("09120000001")
        bob = _user("09120000002")
        _client(alice).post(_ADDRESSES_URL, _VALID_BODY, format="json")

        response = _client(bob).get(_ADDRESSES_URL)

        assert response.data == []

    def test_default_address_is_listed_first(self) -> None:
        client = _client(_user("09120000001"))
        client.post(_ADDRESSES_URL, _VALID_BODY, format="json")
        second = client.post(_ADDRESSES_URL, {**_VALID_BODY, "city": "Shiraz"}, format="json").data
        client.post(f"{_ADDRESSES_URL}{second['id']}/default/")

        response = client.get(_ADDRESSES_URL)

        assert response.data[0]["id"] == second["id"]
        assert response.data[0]["is_default"] is True


class TestUpdateAddress:
    def test_owner_can_update_their_address(self) -> None:
        client = _client(_user("09120000001"))
        address_id = client.post(_ADDRESSES_URL, _VALID_BODY, format="json").data["id"]

        response = client.put(
            f"{_ADDRESSES_URL}{address_id}/", {**_VALID_BODY, "city": "Shiraz"}, format="json"
        )

        assert response.status_code == 200
        assert response.data["city"] == "Shiraz"

    def test_update_never_changes_default_status(self) -> None:
        client = _client(_user("09120000001"))
        address_id = client.post(_ADDRESSES_URL, _VALID_BODY, format="json").data["id"]

        response = client.put(
            f"{_ADDRESSES_URL}{address_id}/", {**_VALID_BODY, "city": "Shiraz"}, format="json"
        )

        assert response.data["is_default"] is True

    def test_another_user_gets_404_not_the_address(self) -> None:
        owner = _user("09120000001")
        intruder = _user("09120000002")
        address_id = _client(owner).post(_ADDRESSES_URL, _VALID_BODY, format="json").data["id"]

        response = _client(intruder).put(
            f"{_ADDRESSES_URL}{address_id}/", {**_VALID_BODY, "city": "Hijacked"}, format="json"
        )

        assert response.status_code == 404

    def test_a_malformed_id_is_a_404(self) -> None:
        client = _client(_user("09120000001"))

        response = client.put(f"{_ADDRESSES_URL}not-an-id!/", _VALID_BODY, format="json")

        assert response.status_code == 404

    def test_invalid_fields_on_update_are_a_400(self) -> None:
        client = _client(_user("09120000001"))
        address_id = client.post(_ADDRESSES_URL, _VALID_BODY, format="json").data["id"]

        response = client.put(
            f"{_ADDRESSES_URL}{address_id}/", {**_VALID_BODY, "postal_code": "bad"}, format="json"
        )

        assert response.status_code == 400


class TestDeleteAddress:
    def test_owner_can_delete_their_address(self) -> None:
        client = _client(_user("09120000001"))
        address_id = client.post(_ADDRESSES_URL, _VALID_BODY, format="json").data["id"]

        response = client.delete(f"{_ADDRESSES_URL}{address_id}/")

        assert response.status_code == 204
        assert client.get(_ADDRESSES_URL).data == []

    def test_another_user_cannot_delete_it(self) -> None:
        owner = _user("09120000001")
        intruder = _user("09120000002")
        address_id = _client(owner).post(_ADDRESSES_URL, _VALID_BODY, format="json").data["id"]

        response = _client(intruder).delete(f"{_ADDRESSES_URL}{address_id}/")

        assert response.status_code == 404
        assert len(_client(owner).get(_ADDRESSES_URL).data) == 1

    def test_deleting_a_malformed_id_is_a_404(self) -> None:
        client = _client(_user("09120000001"))

        assert client.delete(f"{_ADDRESSES_URL}not-an-id!/").status_code == 404


class TestSetDefaultAddress:
    def test_owner_can_change_the_default(self) -> None:
        client = _client(_user("09120000001"))
        first_id = client.post(_ADDRESSES_URL, _VALID_BODY, format="json").data["id"]
        second_id = client.post(
            _ADDRESSES_URL, {**_VALID_BODY, "city": "Shiraz"}, format="json"
        ).data["id"]

        response = client.post(f"{_ADDRESSES_URL}{second_id}/default/")

        assert response.status_code == 200
        assert response.data["is_default"] is True
        addresses = {a["id"]: a["is_default"] for a in client.get(_ADDRESSES_URL).data}
        assert addresses[first_id] is False
        assert addresses[second_id] is True

    def test_another_user_cannot_set_it_default(self) -> None:
        owner = _user("09120000001")
        intruder = _user("09120000002")
        address_id = _client(owner).post(_ADDRESSES_URL, _VALID_BODY, format="json").data["id"]

        response = _client(intruder).post(f"{_ADDRESSES_URL}{address_id}/default/")

        assert response.status_code == 404

    def test_setting_default_on_a_malformed_id_is_a_404(self) -> None:
        client = _client(_user("09120000001"))

        assert client.post(f"{_ADDRESSES_URL}not-an-id!/default/").status_code == 404
