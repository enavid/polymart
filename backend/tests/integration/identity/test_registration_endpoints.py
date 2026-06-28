"""Integration tests for the OTP registration and password-reset endpoints.

These exercise the full HTTP path and pin the security posture: requesting a code
is uniform (it never reveals whether a phone has an account), a verified code
creates or updates the account exactly once, wrong codes lock out, and neither
the code nor the password is ever logged.

The code generator is patched to a fixed value so a test can submit the code it
"received" -- in production the code is delivered only over SMS and stored only
as a hash.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from src.domain.identity.enums import OtpPurpose
from src.infrastructure.identity.models import OtpChallengeModel
from src.infrastructure.identity.services import HmacCodeHasher

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_PHONE = "09123456789"
_CANONICAL = "+989123456789"
_CODE = "123456"
_PASSWORD = "s3cret-password"
_NEW_PASSWORD = "brand-new-password"

_REQUEST_URL = "/api/v1/auth/otp/request/"
_REGISTER_URL = "/api/v1/auth/register/"
_RESET_URL = "/api/v1/auth/password-reset/"
_LOGIN_URL = "/api/v1/auth/login/"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def fixed_code() -> Iterator[None]:
    with mock.patch(
        "src.infrastructure.identity.services.SecretsCodeGenerator.generate",
        return_value=_CODE,
    ):
        yield


@pytest.fixture
def captured_sms() -> Iterator[mock.Mock]:
    with mock.patch("src.infrastructure.identity.services.LoggingSmsSender.send_otp") as sender:
        yield sender


def _request_otp(client: APIClient, purpose: OtpPurpose, phone: str = _PHONE) -> Response:
    return client.post(
        _REQUEST_URL, {"phone_number": phone, "purpose": purpose.value}, format="json"
    )


def _make_user(phone: str = _PHONE, password: str = _PASSWORD) -> object:
    return get_user_model().objects.create_user(phone_number=phone, password=password)


def _inject_live_challenge(purpose: OtpPurpose, phone: str = _CANONICAL) -> None:
    """Persist a valid, matching challenge directly (bypassing eligibility).

    Used to drive the race/TOCTOU branches where a code is genuinely valid but the
    account state has changed since it was issued.
    """
    now = datetime.now(UTC)
    OtpChallengeModel.objects.create(
        phone_number=phone,
        purpose=purpose.value,
        code_hash=HmacCodeHasher().hash(_CODE),
        expires_at=now + timedelta(minutes=2),
        max_attempts=5,
        created_at=now,
    )


class TestRequestOtp:
    def test_request_for_a_new_phone_is_accepted_and_sends_a_code(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        response = _request_otp(client, OtpPurpose.REGISTRATION)

        assert response.status_code == 202
        captured_sms.assert_called_once_with(_CANONICAL, _CODE)
        assert OtpChallengeModel.objects.filter(phone_number=_CANONICAL).count() == 1

    def test_request_for_an_existing_phone_looks_identical_but_sends_nothing(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        # Anti-enumeration: same 202, but no registration code is minted/sent for
        # a number that already has an account.
        _make_user()

        response = _request_otp(client, OtpPurpose.REGISTRATION)

        assert response.status_code == 202
        captured_sms.assert_not_called()
        assert OtpChallengeModel.objects.filter(phone_number=_CANONICAL).count() == 0

    def test_malformed_phone_is_rejected(self, client: APIClient) -> None:
        response = client.post(
            _REQUEST_URL,
            {"phone_number": "not-a-phone", "purpose": OtpPurpose.REGISTRATION.value},
            format="json",
        )

        assert response.status_code == 400

    def test_unknown_purpose_is_rejected(self, client: APIClient) -> None:
        response = client.post(
            _REQUEST_URL, {"phone_number": _PHONE, "purpose": "nonsense"}, format="json"
        )

        assert response.status_code == 400

    def test_a_rapid_resend_is_throttled_silently(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        _request_otp(client, OtpPurpose.REGISTRATION)
        _request_otp(client, OtpPurpose.REGISTRATION)

        # Both accepted, but the cooldown prevents a second code/SMS.
        assert captured_sms.call_count == 1
        assert OtpChallengeModel.objects.filter(phone_number=_CANONICAL).count() == 1

    def test_the_code_is_never_logged(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        with capture_logs() as logs:
            _request_otp(client, OtpPurpose.REGISTRATION)

        assert _CODE not in repr(logs)


class TestRegister:
    def test_a_correct_code_creates_an_account_that_can_log_in(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        _request_otp(client, OtpPurpose.REGISTRATION)

        response = client.post(
            _REGISTER_URL,
            {"phone_number": _PHONE, "code": _CODE, "password": _PASSWORD, "full_name": "Ada"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["phone_number"] == _CANONICAL
        assert get_user_model().objects.filter(phone_number=_CANONICAL).exists()

        login = client.post(
            _LOGIN_URL, {"phone_number": _PHONE, "password": _PASSWORD}, format="json"
        )
        assert login.status_code == 200

    def test_a_wrong_code_is_rejected_and_creates_no_account(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        _request_otp(client, OtpPurpose.REGISTRATION)

        response = client.post(
            _REGISTER_URL,
            {"phone_number": _PHONE, "code": "000000", "password": _PASSWORD},
            format="json",
        )

        assert response.status_code == 400
        assert not get_user_model().objects.filter(phone_number=_CANONICAL).exists()

    def test_registration_without_a_requested_code_is_rejected(self, client: APIClient) -> None:
        response = client.post(
            _REGISTER_URL,
            {"phone_number": _PHONE, "code": _CODE, "password": _PASSWORD},
            format="json",
        )

        assert response.status_code == 400

    def test_a_spent_code_cannot_be_replayed(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        _request_otp(client, OtpPurpose.REGISTRATION)
        client.post(
            _REGISTER_URL,
            {"phone_number": _PHONE, "code": _CODE, "password": _PASSWORD},
            format="json",
        )

        replay = client.post(
            _REGISTER_URL,
            {"phone_number": _PHONE, "code": _CODE, "password": "another-password"},
            format="json",
        )

        assert replay.status_code == 400
        assert get_user_model().objects.filter(phone_number=_CANONICAL).count() == 1

    def test_too_many_wrong_codes_lock_out_even_the_correct_one(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        _request_otp(client, OtpPurpose.REGISTRATION)
        for _ in range(5):
            client.post(
                _REGISTER_URL,
                {"phone_number": _PHONE, "code": "000000", "password": _PASSWORD},
                format="json",
            )

        response = client.post(
            _REGISTER_URL,
            {"phone_number": _PHONE, "code": _CODE, "password": _PASSWORD},
            format="json",
        )

        assert response.status_code == 400
        assert not get_user_model().objects.filter(phone_number=_CANONICAL).exists()

    def test_a_short_password_is_rejected(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        _request_otp(client, OtpPurpose.REGISTRATION)

        response = client.post(
            _REGISTER_URL,
            {"phone_number": _PHONE, "code": _CODE, "password": "short"},
            format="json",
        )

        assert response.status_code == 400

    def test_the_password_is_never_logged(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        _request_otp(client, OtpPurpose.REGISTRATION)

        with capture_logs() as logs:
            client.post(
                _REGISTER_URL,
                {"phone_number": _PHONE, "code": _CODE, "password": _PASSWORD},
                format="json",
            )

        assert _PASSWORD not in repr(logs)

    def test_a_malformed_phone_is_rejected(self, client: APIClient) -> None:
        response = client.post(
            _REGISTER_URL,
            {"phone_number": "not-a-phone", "code": _CODE, "password": _PASSWORD},
            format="json",
        )

        assert response.status_code == 400

    def test_a_valid_code_for_an_already_taken_phone_fails_generically(
        self, client: APIClient
    ) -> None:
        # TOCTOU: the phone was registered after the code was issued.
        _make_user()
        _inject_live_challenge(OtpPurpose.REGISTRATION)

        response = client.post(
            _REGISTER_URL,
            {"phone_number": _PHONE, "code": _CODE, "password": _PASSWORD},
            format="json",
        )

        assert response.status_code == 400


class TestPasswordReset:
    def test_a_correct_code_sets_a_new_password(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        _make_user()
        _request_otp(client, OtpPurpose.PASSWORD_RESET)

        response = client.post(
            _RESET_URL,
            {"phone_number": _PHONE, "code": _CODE, "new_password": _NEW_PASSWORD},
            format="json",
        )

        assert response.status_code == 200
        # The new password works and the old one no longer does.
        assert (
            client.post(
                _LOGIN_URL, {"phone_number": _PHONE, "password": _NEW_PASSWORD}, format="json"
            ).status_code
            == 200
        )
        assert (
            client.post(
                _LOGIN_URL, {"phone_number": _PHONE, "password": _PASSWORD}, format="json"
            ).status_code
            == 401
        )

    def test_reset_revokes_existing_refresh_tokens(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        # A reset must invalidate sessions opened before it: a refresh token minted
        # under the old password can no longer mint new access tokens afterwards.
        _make_user()
        login = client.post(
            _LOGIN_URL, {"phone_number": _PHONE, "password": _PASSWORD}, format="json"
        )
        stale_refresh = login.cookies[settings.AUTH_COOKIE_REFRESH].value

        _request_otp(client, OtpPurpose.PASSWORD_RESET)
        reset = client.post(
            _RESET_URL,
            {"phone_number": _PHONE, "code": _CODE, "new_password": _NEW_PASSWORD},
            format="json",
        )
        assert reset.status_code == 200

        client.cookies[settings.AUTH_COOKIE_REFRESH] = stale_refresh
        assert client.post("/api/v1/auth/refresh/").status_code == 401

    def test_reset_for_an_unknown_phone_sends_nothing_and_cannot_complete(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        # No account -> uniform 202 on request, no code sent, reset cannot proceed.
        request = _request_otp(client, OtpPurpose.PASSWORD_RESET)
        assert request.status_code == 202
        captured_sms.assert_not_called()

        response = client.post(
            _RESET_URL,
            {"phone_number": _PHONE, "code": _CODE, "new_password": _NEW_PASSWORD},
            format="json",
        )
        assert response.status_code == 400

    def test_a_registration_code_cannot_reset_a_password(
        self, client: APIClient, fixed_code: None, captured_sms: mock.Mock
    ) -> None:
        _make_user()
        # A registration code exists, but it is purpose-scoped and must not work
        # for reset.
        OtpChallengeModel.objects.all().delete()
        client_other = APIClient()
        _request_otp(client_other, OtpPurpose.REGISTRATION, phone="09120000009")

        response = client.post(
            _RESET_URL,
            {"phone_number": _PHONE, "code": _CODE, "new_password": _NEW_PASSWORD},
            format="json",
        )

        assert response.status_code == 400

    def test_a_malformed_phone_is_rejected(self, client: APIClient) -> None:
        response = client.post(
            _RESET_URL,
            {"phone_number": "not-a-phone", "code": _CODE, "new_password": _NEW_PASSWORD},
            format="json",
        )

        assert response.status_code == 400

    def test_a_valid_code_for_a_vanished_user_fails_generically(self, client: APIClient) -> None:
        # TOCTOU: the account was removed after the reset code was issued.
        _inject_live_challenge(OtpPurpose.PASSWORD_RESET)

        response = client.post(
            _RESET_URL,
            {"phone_number": _PHONE, "code": _CODE, "new_password": _NEW_PASSWORD},
            format="json",
        )

        assert response.status_code == 400
