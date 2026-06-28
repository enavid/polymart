"""Django ORM implementation of the catalog repository ports."""

from __future__ import annotations

import structlog
from django.db import IntegrityError, transaction

from src.application.catalog.ports import AttributeRepository
from src.domain.catalog.entities import Attribute
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    AttributeNotFoundError,
)
from src.infrastructure.catalog.mappers import apply_scalar_fields, to_domain
from src.infrastructure.catalog.models import AttributeChoiceModel, AttributeModel

logger = structlog.get_logger(__name__)


class DjangoAttributeRepository(AttributeRepository):
    """Persist attributes with the Django ORM, returning domain entities."""

    def add(self, attribute: Attribute) -> Attribute:
        model = apply_scalar_fields(attribute, AttributeModel())
        try:
            # The attribute and all its choices are one definition: persist them
            # together so a failed choice insert never leaves a half-built record.
            with transaction.atomic():
                model.save()
                self._save_choices(attribute, model)
        except IntegrityError as exc:
            # Unique-constraint violation on code -> domain-level conflict. Reaching
            # here means a concurrent insert won the race after the use case's
            # pre-check passed.
            logger.warning("attribute_insert_race_lost", code=attribute.code.value)
            raise AttributeAlreadyExistsError(attribute.code.value) from exc
        return to_domain(model)

    @staticmethod
    def _save_choices(attribute: Attribute, model: AttributeModel) -> None:
        AttributeChoiceModel.objects.bulk_create(
            AttributeChoiceModel(
                attribute=model,
                value=choice.value,
                label=choice.label,
                position=position,
            )
            for position, choice in enumerate(attribute.choices)
        )

    def get_by_code(self, code: str) -> Attribute:
        try:
            model = AttributeModel.objects.prefetch_related("choices").get(code=code)
        except AttributeModel.DoesNotExist as exc:
            raise AttributeNotFoundError(code) from exc
        return to_domain(model)

    def exists_by_code(self, code: str) -> bool:
        return AttributeModel.objects.filter(code=code).exists()

    def list_all(self) -> list[Attribute]:
        models = AttributeModel.objects.prefetch_related("choices").all()
        return [to_domain(model) for model in models]
