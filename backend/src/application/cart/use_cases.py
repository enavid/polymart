"""Cart use cases (interactors).

Each use case orchestrates the domain to fulfil one application intent: pure
orchestration, dependencies via constructor injection, business rules in the
domain, side effects (logging) observable.

A cart is pre-order: adding or removing a line moves neither money nor inventory,
so -- unlike the catalog's price/stock mutations -- these are *not* written to the
audit trail. They emit structured logs only (never any PII: the actor is the stable
user id, never the phone number, and prices are never logged). Money-sensitive
auditing begins at order placement, in a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.application.cart.ports import CartRepository, ChannelReader, VariantPricingReader
from src.domain.cart.entities import Cart
from src.domain.cart.exceptions import (
    UnknownChannelError,
    VariantNotFoundError,
    VariantNotPurchasableError,
)
from src.domain.cart.services import PricedCart, price_cart
from src.domain.cart.value_objects import CartQuantity, ChannelRef, Money, Sku

logger = structlog.get_logger(__name__)


def _resolve_currency(channels: ChannelReader, channel: str) -> str:
    """Return the channel's currency or raise if the channel does not exist."""
    currency = channels.currency_of(channel)
    if currency is None:
        raise UnknownChannelError(channel)
    return currency


def _price(cart: Cart, pricing: VariantPricingReader, currency: str) -> PricedCart:
    """Resolve each line's current unit price and project the priced cart."""
    unit_prices: dict[str, Money] = {}
    for line in cart.lines:
        price = pricing.price_of(line.sku.value, cart.channel.value)
        if price is not None:
            unit_prices[line.sku.value] = price
    return price_cart(cart, unit_prices, currency)


@dataclass(frozen=True)
class GetCartQuery:
    """Input for reading a shopper's cart in a channel."""

    owner: str
    channel: str


class GetCart:
    """Read the owner's cart for a channel, priced at current prices."""

    def __init__(
        self,
        carts: CartRepository,
        pricing: VariantPricingReader,
        channels: ChannelReader,
    ) -> None:
        self._carts = carts
        self._pricing = pricing
        self._channels = channels

    def execute(self, query: GetCartQuery) -> PricedCart:
        currency = _resolve_currency(self._channels, query.channel)
        cart = self._carts.get(query.owner, query.channel)
        priced = _price(cart, self._pricing, currency)
        logger.debug(
            "cart_read", owner=query.owner, channel=query.channel, line_count=len(priced.lines)
        )
        return priced


@dataclass(frozen=True)
class AddCartItemCommand:
    """Input for adding (or incrementing) a line in a shopper's cart."""

    owner: str
    channel: str
    sku: str
    quantity: int


class AddCartItem:
    """Add a variant to the cart, or increase its quantity if already present.

    A variant can only be added if it exists and has a price in the channel (else it
    could never be sold there); both are checked before the line is persisted, so a
    stored line is always purchasable at add time.
    """

    def __init__(
        self,
        carts: CartRepository,
        pricing: VariantPricingReader,
        channels: ChannelReader,
    ) -> None:
        self._carts = carts
        self._pricing = pricing
        self._channels = channels

    def execute(self, command: AddCartItemCommand) -> PricedCart:
        # Build value objects first: a malformed sku/quantity/channel fails fast.
        sku = Sku(command.sku)
        quantity = CartQuantity(command.quantity)
        channel = ChannelRef(command.channel)

        currency = _resolve_currency(self._channels, channel.value)
        self._require_purchasable(sku, channel)

        # The add runs inside the repository's locked read-modify-write so a
        # concurrent add for the same cart cannot lose this line.
        saved = self._carts.apply(
            command.owner, channel.value, lambda cart: cart.add_item(sku, quantity)
        )
        logger.info(
            "cart_item_added",
            owner=command.owner,
            channel=channel.value,
            sku=sku.value,
            quantity=quantity.value,
            line_count=len(saved.lines),
        )
        return _price(saved, self._pricing, currency)

    def _require_purchasable(self, sku: Sku, channel: ChannelRef) -> None:
        if not self._pricing.exists(sku.value):
            logger.warning("cart_add_rejected_unknown_variant", sku=sku.value)
            raise VariantNotFoundError(sku.value)
        if self._pricing.price_of(sku.value, channel.value) is None:
            logger.warning(
                "cart_add_rejected_unpriced_variant", sku=sku.value, channel=channel.value
            )
            raise VariantNotPurchasableError(sku.value, channel.value)


@dataclass(frozen=True)
class UpdateCartItemCommand:
    """Input for setting the absolute quantity of an existing cart line."""

    owner: str
    channel: str
    sku: str
    quantity: int


class UpdateCartItem:
    """Set an existing line's quantity to an absolute value (never creates a line)."""

    def __init__(
        self,
        carts: CartRepository,
        pricing: VariantPricingReader,
        channels: ChannelReader,
    ) -> None:
        self._carts = carts
        self._pricing = pricing
        self._channels = channels

    def execute(self, command: UpdateCartItemCommand) -> PricedCart:
        sku = Sku(command.sku)
        quantity = CartQuantity(command.quantity)
        channel = ChannelRef(command.channel)

        currency = _resolve_currency(self._channels, channel.value)
        # Under the repository lock: raises CartLineNotFoundError (a 404) if the cart
        # has no such line, in which case nothing is written.
        saved = self._carts.apply(
            command.owner, channel.value, lambda cart: cart.set_item(sku, quantity)
        )
        logger.info(
            "cart_item_updated",
            owner=command.owner,
            channel=channel.value,
            sku=sku.value,
            quantity=quantity.value,
            line_count=len(saved.lines),
        )
        return _price(saved, self._pricing, currency)


@dataclass(frozen=True)
class RemoveCartItemCommand:
    """Input for removing a line from a shopper's cart."""

    owner: str
    channel: str
    sku: str


class RemoveCartItem:
    """Remove a line from the cart (raises if the cart does not contain it)."""

    def __init__(
        self,
        carts: CartRepository,
        pricing: VariantPricingReader,
        channels: ChannelReader,
    ) -> None:
        self._carts = carts
        self._pricing = pricing
        self._channels = channels

    def execute(self, command: RemoveCartItemCommand) -> PricedCart:
        sku = Sku(command.sku)
        channel = ChannelRef(command.channel)

        currency = _resolve_currency(self._channels, channel.value)
        # Under the repository lock: raises CartLineNotFoundError (a 404) if the cart
        # has no such line, in which case nothing is written.
        saved = self._carts.apply(command.owner, channel.value, lambda cart: cart.remove_item(sku))
        logger.info(
            "cart_item_removed",
            owner=command.owner,
            channel=channel.value,
            sku=sku.value,
            line_count=len(saved.lines),
        )
        return _price(saved, self._pricing, currency)
