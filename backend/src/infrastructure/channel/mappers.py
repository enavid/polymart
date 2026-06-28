"""Mapping between the Channel domain entity and its ORM representation."""

from __future__ import annotations

from src.domain.channel.entities import Channel
from src.domain.channel.value_objects import ChannelSlug, Currency
from src.infrastructure.channel.models import ChannelModel


def to_domain(model: ChannelModel) -> Channel:
    """Rebuild a domain entity from a persisted row."""
    return Channel(
        id=model.pk,
        slug=ChannelSlug(model.slug),
        name=model.name,
        currency=Currency(model.currency_code),
        is_active=model.is_active,
    )


def apply_to_model(channel: Channel, model: ChannelModel) -> ChannelModel:
    """Copy domain state onto an ORM instance (for create or update)."""
    model.slug = channel.slug.value
    model.name = channel.name
    model.currency_code = channel.currency.code
    model.is_active = channel.is_active
    return model
