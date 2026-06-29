"""Concrete adapters for the identity OTP ports.

Cryptographically secure code generation, keyed one-way hashing, SMS delivery,
and a system clock. The SMS sender is the seam where a real Iranian gateway
(Kavenegar, Ghasedak, ...) plugs in later; for now it logs that a code was
dispatched -- never the code itself in production, though DEBUG logs the code so
the OTP flow is completable locally without a real gateway.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime
from hashlib import sha256

import structlog
from django.conf import settings

from src.application.identity.ports import Clock, CodeGenerator, CodeHasher, SmsSender

logger = structlog.get_logger(__name__)

# A 6-digit numeric code: familiar to users and large enough that, paired with a
# 2-minute TTL and a 5-attempt lockout, brute force is infeasible.
_CODE_DIGITS = 6
_CODE_UPPER_BOUND = 10**_CODE_DIGITS
# Keep the last two national digits for support/debugging; hide the rest (PII).
_VISIBLE_TAIL = 2


class SecretsCodeGenerator(CodeGenerator):
    """Generate codes with the cryptographically secure ``secrets`` module."""

    def generate(self) -> str:
        return f"{secrets.randbelow(_CODE_UPPER_BOUND):0{_CODE_DIGITS}d}"


class HmacCodeHasher(CodeHasher):
    """Keyed HMAC-SHA256 hashing of codes.

    Keyed by ``SECRET_KEY`` so the tiny (10^6) code space cannot be brute-forced
    offline from a leaked row without also stealing the key. Comparison is
    constant-time to avoid leaking the code through timing.
    """

    def hash(self, code: str) -> str:
        return self._digest(code)

    def verify(self, code: str, code_hash: str) -> bool:
        return hmac.compare_digest(self._digest(code), code_hash)

    @staticmethod
    def _digest(code: str) -> str:
        key = settings.SECRET_KEY.encode()
        return hmac.new(key, code.encode(), sha256).hexdigest()


class LoggingSmsSender(SmsSender):
    """Stand-in SMS gateway: logs that a code was dispatched.

    In production the code is intentionally never logged -- it is a live
    credential. In local development (``DEBUG=True``) there is no real gateway,
    so the code (and full phone) are logged as well, letting a developer complete
    the OTP flow without an SMS provider. The branch is guarded by ``DEBUG`` so it
    can never fire in production.
    """

    def send_otp(self, phone_number: str, code: str) -> None:
        if settings.DEBUG:
            logger.warning("otp_dispatched_dev", phone=phone_number, code=code)
            return
        # ``code`` is intentionally not logged: it is a live credential.
        logger.info("otp_dispatched", phone=_mask_phone(phone_number))


class SystemClock(Clock):
    """The real wall clock, in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)


def _mask_phone(phone_number: str) -> str:
    """Reduce a phone number to a non-identifying form for logs."""
    if len(phone_number) <= _VISIBLE_TAIL:
        return "*" * len(phone_number)
    return "*" * (len(phone_number) - _VISIBLE_TAIL) + phone_number[-_VISIBLE_TAIL:]
