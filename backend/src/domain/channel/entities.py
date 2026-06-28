"""The Channel aggregate root.

A channel is a first-class selling context: it bundles the currency, locale, and
(later) pricing/tax/inventory configuration that make one storefront distinct
from another on the same installation. Everything downstream is scoped to it.

This is pure Python -- no Django, no DRF, no ORM.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.channel.exceptions import InvalidChannelNameError
from src.domain.channel.value_objects import ChannelSlug, Currency

_NAME_MAX_LENGTH = 255


@dataclass
class Channel:
    """A selling channel.

    Identity is the database ``id`` once persisted, but the ``slug`` is the
    stable business key used everywhere in the API.
    """

    slug: ChannelSlug
    name: str
    currency: Currency
    is_active: bool = True
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        self.name = self._validated_name(self.name)

    @staticmethod
    def _validated_name(raw: str) -> str:
        name = raw.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidChannelNameError(raw)
        return name

    def activate(self) -> bool:
        """Mark the channel active. Returns whether the state changed."""
        return self.set_active(active=True)

    def deactivate(self) -> bool:
        """Mark the channel inactive. Returns whether the state changed."""
        return self.set_active(active=False)

    def set_active(self, *, active: bool) -> bool:
        """Idempotently set the active flag, returning True if it changed."""
        if self.is_active == active:
            return False
        self.is_active = active
        return True
