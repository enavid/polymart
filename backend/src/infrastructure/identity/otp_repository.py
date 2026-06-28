"""Django ORM implementation of the OTP repository port."""

from __future__ import annotations

from typing import cast

from django.db import transaction

from src.application.identity.ports import OtpRepository
from src.domain.identity.entities import OtpChallenge
from src.domain.identity.enums import OtpPurpose
from src.infrastructure.identity.models import OtpChallengeModel
from src.infrastructure.identity.otp_mappers import apply_to_model, to_domain


class DjangoOtpRepository(OtpRepository):
    """Persist OTP challenges with the Django ORM, returning domain entities."""

    def save(self, challenge: OtpChallenge) -> OtpChallenge:
        if challenge.id is None:
            return self._insert(challenge)
        return self._update(challenge)

    def get_latest(self, phone_number: str, purpose: OtpPurpose) -> OtpChallenge | None:
        # Default ordering is "-created_at", so .first() is the newest challenge.
        model = OtpChallengeModel.objects.filter(
            phone_number=phone_number, purpose=purpose.value
        ).first()
        return to_domain(model) if model is not None else None

    def _insert(self, challenge: OtpChallenge) -> OtpChallenge:
        model = apply_to_model(challenge, OtpChallengeModel())
        with transaction.atomic():
            model.save()
        challenge.id = model.pk
        return challenge

    def _update(self, challenge: OtpChallenge) -> OtpChallenge:
        # Lock the row for the read-modify-write so concurrent verifications cannot
        # lose an attempt increment to a last-write-wins race. No-op on SQLite.
        # Reached only via save() when id is set, so the cast is sound.
        with transaction.atomic():
            model = OtpChallengeModel.objects.select_for_update().get(pk=cast(int, challenge.id))
            apply_to_model(challenge, model)
            model.save(update_fields=["attempts", "consumed_at"])
        return challenge
