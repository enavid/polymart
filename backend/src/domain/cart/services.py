"""Domain services for the cart context (pure Python, no framework).

Pricing spans the whole cart and the current catalog prices, so it belongs to no
single entity. The use case resolves each variant's current unit price (via a
reader port) and hands the mapping here; this service does the money arithmetic --
line totals and the cart total -- with exact ``Decimal`` maths and no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.domain.cart.entities import Cart
from src.domain.cart.exceptions import CurrencyMismatchError
from src.domain.cart.value_objects import CartQuantity, Money, Sku


@dataclass(frozen=True)
class PricedLine:
    """One cart line resolved against the current price.

    ``unit_price`` and ``line_total`` are ``None`` when the variant has no price in
    the cart's channel (it became unpurchasable after it was added); such a line is
    kept visible but marked ``available = False`` and excluded from the total.
    """

    sku: Sku
    quantity: CartQuantity
    unit_price: Money | None
    line_total: Money | None
    available: bool


@dataclass(frozen=True)
class PricedCart:
    """A cart projected with current prices: its lines plus the summed total.

    The total is in the channel's currency and sums only the available lines, so an
    unpurchasable line never silently inflates or invalidates it.
    """

    channel: str
    currency: str
    lines: tuple[PricedLine, ...]
    total: Money


def price_cart(cart: Cart, unit_prices: Mapping[str, Money], currency: str) -> PricedCart:
    """Project ``cart`` with the supplied per-SKU unit prices.

    ``unit_prices`` maps a line's SKU to its current unit price (absent when the
    variant has no price in the channel). Every present price must be in the cart's
    currency; a mismatch is refused rather than summed into a meaningless total.
    """
    total = Money.zero(currency)
    priced: list[PricedLine] = []
    for line in cart.lines:
        unit_price = unit_prices.get(line.sku.value)
        if unit_price is None:
            priced.append(_unavailable_line(line.sku, line.quantity))
            continue
        if unit_price.currency != currency:
            raise CurrencyMismatchError(currency, unit_price.currency)
        line_total = unit_price.times(line.quantity)
        total = total.add(line_total)
        priced.append(
            PricedLine(
                sku=line.sku,
                quantity=line.quantity,
                unit_price=unit_price,
                line_total=line_total,
                available=True,
            )
        )
    return PricedCart(
        channel=cart.channel.value,
        currency=currency,
        lines=tuple(priced),
        total=total,
    )


def _unavailable_line(sku: Sku, quantity: CartQuantity) -> PricedLine:
    return PricedLine(
        sku=sku,
        quantity=quantity,
        unit_price=None,
        line_total=None,
        available=False,
    )
