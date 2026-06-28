"""Django ORM implementation of the channel repository port."""
from __future__ import annotations

from django.db import IntegrityError, transaction

from src.application.channel.ports import ChannelRepository
from src.domain.channel.entities import Channel
from src.domain.channel.exceptions import ChannelAlreadyExistsError, ChannelNotFoundError
from src.infrastructure.channel.mappers import apply_to_model, to_domain
from src.infrastructure.channel.models import ChannelModel


class DjangoChannelRepository(ChannelRepository):
    """Persist channels with the Django ORM, returning domain entities."""

    def add(self, channel: Channel) -> Channel:
        model = apply_to_model(channel, ChannelModel())
        try:
            with transaction.atomic():
                model.save()
        except IntegrityError as exc:
            # Unique-constraint violation on slug -> domain-level conflict.
            raise ChannelAlreadyExistsError(channel.slug.value) from exc
        return to_domain(model)

    def get_by_slug(self, slug: str) -> Channel:
        try:
            model = ChannelModel.objects.get(slug=slug)
        except ChannelModel.DoesNotExist as exc:
            raise ChannelNotFoundError(slug) from exc
        return to_domain(model)

    def exists_by_slug(self, slug: str) -> bool:
        return ChannelModel.objects.filter(slug=slug).exists()

    def list_all(self) -> list[Channel]:
        return [to_domain(model) for model in ChannelModel.objects.all()]

    def update(self, channel: Channel) -> Channel:
        try:
            model = ChannelModel.objects.get(slug=channel.slug.value)
        except ChannelModel.DoesNotExist as exc:
            raise ChannelNotFoundError(channel.slug.value) from exc
        apply_to_model(channel, model)
        model.save(update_fields=["name", "currency_code", "is_active", "updated_at"])
        return to_domain(model)
