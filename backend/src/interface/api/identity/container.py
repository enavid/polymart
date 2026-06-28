"""Composition root for the identity OTP slice.

The only place that wires concrete infrastructure adapters into the OTP use
cases. Views depend on these factories, never on the infrastructure layer
directly, so the dependency rule keeps pointing inward.
"""

from __future__ import annotations

from src.application.identity.use_cases import (
    OtpVerifier,
    RegisterUser,
    RequestOtp,
    ResetPassword,
)
from src.infrastructure.identity.otp_repository import DjangoOtpRepository
from src.infrastructure.identity.services import (
    HmacCodeHasher,
    LoggingSmsSender,
    SecretsCodeGenerator,
    SystemClock,
)
from src.infrastructure.identity.token_revoker import SimpleJwtTokenRevoker
from src.infrastructure.identity.user_directory import DjangoUserDirectory


def _verifier() -> OtpVerifier:
    return OtpVerifier(otp_repo=DjangoOtpRepository(), hasher=HmacCodeHasher(), clock=SystemClock())


def build_request_otp() -> RequestOtp:
    return RequestOtp(
        otp_repo=DjangoOtpRepository(),
        generator=SecretsCodeGenerator(),
        hasher=HmacCodeHasher(),
        sms=LoggingSmsSender(),
        clock=SystemClock(),
        users=DjangoUserDirectory(),
    )


def build_register_user() -> RegisterUser:
    return RegisterUser(verifier=_verifier(), users=DjangoUserDirectory())


def build_reset_password() -> ResetPassword:
    return ResetPassword(
        verifier=_verifier(),
        users=DjangoUserDirectory(),
        tokens=SimpleJwtTokenRevoker(),
    )
