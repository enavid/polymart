"""Identity OTP use cases: request a code, register, reset a password.

These interactors own the application policy of the one-time-code flows --
eligibility, cooldown, expiry, attempt limits, single use -- by orchestrating the
domain entity and the injected ports. They contain no transport or framework
detail and never log the raw code, the password, or the phone number (PII).

Anti-enumeration is a deliberate design choice: ``RequestOtp`` behaves uniformly
(it always succeeds for the caller) whether or not a code was actually minted, so
the endpoint cannot reveal which phone numbers have accounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import structlog

from src.application.identity.ports import (
    Clock,
    CodeGenerator,
    CodeHasher,
    OtpRepository,
    SmsSender,
    TokenRevoker,
    UserDirectory,
)
from src.domain.identity.entities import OtpChallenge
from src.domain.identity.enums import OtpPurpose
from src.domain.identity.exceptions import (
    InvalidOtpError,
    OtpExpiredError,
    OtpMaxAttemptsError,
)
from src.domain.identity.value_objects import PhoneNumber

logger = structlog.get_logger(__name__)

# OTP policy. Short-lived, few guesses, and a resend cooldown to throttle abuse.
_OTP_TTL = timedelta(minutes=2)
_MAX_ATTEMPTS = 5
_RESEND_COOLDOWN = timedelta(seconds=60)


@dataclass(frozen=True)
class RegisteredUser:
    """The outcome of a successful registration (no secrets)."""

    id: int
    phone_number: str
    full_name: str
    email: str


class OtpVerifier:
    """Shared verification of a submitted code against the latest challenge.

    Centralized so registration and password reset apply identical rules. A wrong
    code is counted against the attempt budget and persisted *before* the failure
    is raised, so the brute-force lockout survives even though the request fails.
    """

    def __init__(self, *, otp_repo: OtpRepository, hasher: CodeHasher, clock: Clock) -> None:
        self._otp_repo = otp_repo
        self._hasher = hasher
        self._clock = clock

    def verify(self, phone_number: str, purpose: OtpPurpose, code: str) -> OtpChallenge:
        """Return the matching, unspent challenge or raise an OTP error."""
        challenge = self._otp_repo.get_latest(phone_number, purpose)
        if challenge is None or challenge.is_consumed:
            raise InvalidOtpError
        if challenge.is_expired(self._clock.now()):
            raise OtpExpiredError
        if challenge.attempts_exhausted:
            raise OtpMaxAttemptsError
        if not self._hasher.verify(code, challenge.code_hash):
            challenge.register_failed_attempt()
            self._otp_repo.save(challenge)
            logger.info("otp_verification_failed", purpose=purpose.value, reason="mismatch")
            raise InvalidOtpError
        return challenge

    def consume(self, challenge: OtpChallenge) -> None:
        """Mark a verified challenge as spent so it cannot be replayed."""
        challenge.consume(self._clock.now())
        self._otp_repo.save(challenge)


class RequestOtp:
    """Issue and deliver a one-time code, uniformly and without enumeration."""

    def __init__(
        self,
        *,
        otp_repo: OtpRepository,
        generator: CodeGenerator,
        hasher: CodeHasher,
        sms: SmsSender,
        clock: Clock,
        users: UserDirectory,
    ) -> None:
        self._otp_repo = otp_repo
        self._generator = generator
        self._hasher = hasher
        self._sms = sms
        self._clock = clock
        self._users = users

    def execute(self, *, phone_number_raw: str, purpose: OtpPurpose) -> None:
        # Validate format first; an invalid phone is a client error, not an
        # account hint, so this is the one non-uniform outcome.
        phone = PhoneNumber(phone_number_raw).value

        if not self._is_eligible(phone, purpose):
            logger.info("otp_request_skipped", purpose=purpose.value, reason="ineligible")
            return
        if self._within_cooldown(phone, purpose):
            logger.info("otp_request_skipped", purpose=purpose.value, reason="cooldown")
            return

        now = self._clock.now()
        code = self._generator.generate()
        challenge = self._otp_repo.save(
            OtpChallenge(
                phone_number=phone,
                purpose=purpose,
                code_hash=self._hasher.hash(code),
                expires_at=now + _OTP_TTL,
                max_attempts=_MAX_ATTEMPTS,
                created_at=now,
            )
        )
        self._sms.send_otp(phone, code)
        logger.info("otp_requested", purpose=purpose.value, challenge_id=challenge.id)

    def _is_eligible(self, phone: str, purpose: OtpPurpose) -> bool:
        # Registration is for new numbers; reset is for existing ones. Mismatches
        # are silently skipped so the response cannot reveal account existence.
        exists = self._users.exists(phone)
        if purpose is OtpPurpose.REGISTRATION:
            return not exists
        return exists

    def _within_cooldown(self, phone: str, purpose: OtpPurpose) -> bool:
        latest = self._otp_repo.get_latest(phone, purpose)
        if latest is None:
            return False
        return self._clock.now() - latest.created_at < _RESEND_COOLDOWN


class RegisterUser:
    """Create an account once a registration code is verified."""

    def __init__(self, *, verifier: OtpVerifier, users: UserDirectory) -> None:
        self._verifier = verifier
        self._users = users

    def execute(
        self, *, phone_number_raw: str, code: str, password: str, full_name: str, email: str
    ) -> RegisteredUser:
        phone = PhoneNumber(phone_number_raw).value
        challenge = self._verifier.verify(phone, OtpPurpose.REGISTRATION, code)
        # Create before consuming: a verification failure must keep its attempt
        # increment, while the unique-phone constraint is the real guard against a
        # duplicate account under a race.
        user_id = self._users.create(phone, password=password, full_name=full_name, email=email)
        self._verifier.consume(challenge)
        logger.info("user_registered", user_id=user_id)
        return RegisteredUser(id=user_id, phone_number=phone, full_name=full_name, email=email)


class ResetPassword:
    """Replace an account's password once a reset code is verified.

    A successful reset also revokes the account's outstanding tokens, so any
    session opened with the old password (or a leaked token) cannot survive it.
    """

    def __init__(
        self, *, verifier: OtpVerifier, users: UserDirectory, tokens: TokenRevoker
    ) -> None:
        self._verifier = verifier
        self._users = users
        self._tokens = tokens

    def execute(self, *, phone_number_raw: str, code: str, new_password: str) -> None:
        phone = PhoneNumber(phone_number_raw).value
        challenge = self._verifier.verify(phone, OtpPurpose.PASSWORD_RESET, code)
        user_id = self._users.set_password(phone, new_password)
        self._verifier.consume(challenge)
        self._tokens.revoke_all(user_id)
        logger.info("password_reset_succeeded", user_id=user_id)
