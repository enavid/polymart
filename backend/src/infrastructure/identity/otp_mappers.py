"""Mapping between the OtpChallenge domain entity and its ORM representation."""

from __future__ import annotations

from src.domain.identity.entities import OtpChallenge
from src.domain.identity.enums import OtpPurpose
from src.infrastructure.identity.models import OtpChallengeModel


def to_domain(model: OtpChallengeModel) -> OtpChallenge:
    """Rebuild a domain entity from a persisted row."""
    return OtpChallenge(
        id=model.pk,
        phone_number=model.phone_number,
        purpose=OtpPurpose(model.purpose),
        code_hash=model.code_hash,
        expires_at=model.expires_at,
        max_attempts=model.max_attempts,
        attempts=model.attempts,
        consumed_at=model.consumed_at,
        created_at=model.created_at,
    )


def apply_to_model(challenge: OtpChallenge, model: OtpChallengeModel) -> OtpChallengeModel:
    """Copy domain state onto an ORM instance (for create or update)."""
    model.phone_number = challenge.phone_number
    model.purpose = challenge.purpose.value
    model.code_hash = challenge.code_hash
    model.expires_at = challenge.expires_at
    model.max_attempts = challenge.max_attempts
    model.attempts = challenge.attempts
    model.consumed_at = challenge.consumed_at
    model.created_at = challenge.created_at
    return model
