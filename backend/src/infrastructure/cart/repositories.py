"""Django ORM implementation of the cart repository ports."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import structlog
from django.db import transaction

from src.application.cart.ports import CartRepository, ChannelReader, VariantPricingReader
from src.domain.cart.entities import Cart, CartLine
from src.domain.cart.value_objects import ChannelRef, Money
from src.infrastructure.cart.mappers import cart_to_domain
from src.infrastructure.cart.models import CartLineModel, CartModel
from src.infrastructure.catalog.models import ProductVariantModel, VariantPriceModel
from src.infrastructure.channel.models import ChannelModel

logger = structlog.get_logger(__name__)


def _owner_pk(owner: str) -> int:
    """Translate the domain's string owner id back to the user's integer primary key.

    The domain owns a stable string id (independent of the database's key type); the
    owner FK is an integer, so the boundary converts here rather than leaking the DB
    type inward.
    """
    return int(owner)


class DjangoCartRepository(CartRepository):
    """Persist carts with the Django ORM, returning domain aggregates."""

    def get(self, owner: str, channel: str) -> Cart:
        model = (
            CartModel.objects.filter(owner_id=_owner_pk(owner), channel_slug=channel)
            .prefetch_related("lines")
            .first()
        )
        if model is None:
            # A missing cart reads as an empty one, so a first read and a first add
            # behave identically (nothing is written until save).
            return Cart(owner=owner, channel=ChannelRef(channel))
        return cart_to_domain(model)

    def apply(self, owner: str, channel: str, mutate: Callable[[Cart], None]) -> Cart:
        # The whole read-modify-write runs under a lock on the cart row, so two
        # concurrent mutations of the same cart cannot both read the same starting
        # state and lose an update. The domain mutation is applied to the *locked*
        # snapshot; only then is the line set replaced (clear + reinsert). If mutate
        # raises (e.g. a missing line), the atomic block rolls back and nothing is
        # written. The lock also serializes the clear+reinsert so it never interleaves
        # into a unique-constraint error on the lines.
        with transaction.atomic():
            model = self._lock_or_create(owner, channel)
            cart = cart_to_domain(model)
            mutate(cart)
            CartLineModel.objects.filter(cart=model).delete()
            self._insert_lines(model, cart.lines)
            # Touch updated_at so the row reflects the mutation even when only lines change.
            model.save(update_fields=["updated_at"])
        return self.get(owner, channel)

    @staticmethod
    def _lock_or_create(owner: str, channel: str) -> CartModel:
        # get_or_create absorbs the create race (it re-gets on a unique violation);
        # the subsequent select_for_update takes the row lock that serializes the
        # line replacement below.
        owner_pk = _owner_pk(owner)
        CartModel.objects.get_or_create(owner_id=owner_pk, channel_slug=channel)
        return CartModel.objects.select_for_update().get(owner_id=owner_pk, channel_slug=channel)

    @staticmethod
    def _insert_lines(model: CartModel, lines: Sequence[CartLine]) -> None:
        CartLineModel.objects.bulk_create(
            CartLineModel(
                cart=model,
                sku=line.sku.value,
                quantity=line.quantity.value,
                position=position,
            )
            for position, line in enumerate(lines)
        )


class DjangoVariantPricingReader(VariantPricingReader):
    """Read a variant's existence and current channel price from the catalog context."""

    def exists(self, sku: str) -> bool:
        return ProductVariantModel.objects.filter(sku=sku).exists()

    def price_of(self, sku: str, channel: str) -> Money | None:
        row = VariantPriceModel.objects.filter(variant__sku=sku, channel_slug=channel).first()
        if row is None:
            return None
        # The catalog stores the amount as a fixed-point Decimal and the currency
        # derived from the channel; rebuild a cart-domain Money (never a float).
        return Money(amount=row.amount, currency=row.currency_code)


class DjangoChannelReader(ChannelReader):
    """Read a channel's currency from the channel context, for cart pricing."""

    def currency_of(self, channel: str) -> str | None:
        return (
            ChannelModel.objects.filter(slug=channel)
            .values_list("currency_code", flat=True)
            .first()
        )
