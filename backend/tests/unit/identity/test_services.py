"""Unit tests for the identity OTP infrastructure services.

Code generation, keyed hashing, SMS dispatch, and the clock. The security-
relevant guarantees: codes are the right shape, hashing is one-way and
constant-time-correct, and dispatch logs never carry the code or a full phone.
"""

from __future__ import annotations

import re
from datetime import UTC

from django.test import override_settings
from structlog.testing import capture_logs

from src.infrastructure.identity.services import (
    HmacCodeHasher,
    LoggingSmsSender,
    SecretsCodeGenerator,
    SystemClock,
)

_CODE_PATTERN = re.compile(r"^\d{6}$")


class TestSecretsCodeGenerator:
    def test_generates_a_six_digit_numeric_code(self) -> None:
        for _ in range(50):
            assert _CODE_PATTERN.match(SecretsCodeGenerator().generate())


class TestHmacCodeHasher:
    def test_hash_does_not_expose_the_code(self) -> None:
        hasher = HmacCodeHasher()

        digest = hasher.hash("123456")

        assert "123456" not in digest

    def test_verifies_a_matching_code(self) -> None:
        hasher = HmacCodeHasher()

        assert hasher.verify("123456", hasher.hash("123456")) is True

    def test_rejects_a_non_matching_code(self) -> None:
        hasher = HmacCodeHasher()

        assert hasher.verify("000000", hasher.hash("123456")) is False


class TestLoggingSmsSender:
    def test_logs_dispatch_without_the_code_or_full_phone(self) -> None:
        with capture_logs() as logs:
            LoggingSmsSender().send_otp("+989123456789", "123456")

        serialized = repr(logs)
        assert "123456" not in serialized
        assert "+989123456789" not in serialized
        assert any(entry["event"] == "otp_dispatched" for entry in logs)

    def test_fully_masks_an_unexpectedly_short_phone(self) -> None:
        # Defensive: a too-short value is never partially revealed.
        with override_settings(DEBUG=False), capture_logs() as logs:
            LoggingSmsSender().send_otp("12", "0")

        assert logs[0]["phone"] == "**"

    @override_settings(DEBUG=True)
    def test_logs_the_code_in_debug_for_local_development(self) -> None:
        # There is no SMS gateway in local dev, so DEBUG surfaces the code (and
        # full phone) in the logs to make the OTP flow completable by hand.
        with capture_logs() as logs:
            LoggingSmsSender().send_otp("+989123456789", "123456")

        assert any(
            entry["event"] == "otp_dispatched_dev" and entry.get("code") == "123456"
            for entry in logs
        )

    @override_settings(DEBUG=False)
    def test_never_logs_the_code_outside_debug(self) -> None:
        # Production (DEBUG=False) must never log the code: it is a live credential.
        with capture_logs() as logs:
            LoggingSmsSender().send_otp("+989123456789", "123456")

        assert "123456" not in repr(logs)
        assert all(entry["event"] != "otp_dispatched_dev" for entry in logs)


class TestSystemClock:
    def test_now_is_timezone_aware_utc(self) -> None:
        assert SystemClock().now().tzinfo == UTC
