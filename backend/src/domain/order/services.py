"""Domain services for the order context (pure Python, no framework).

Assembling an order's lines and total from the priced items spans the whole order and
involves money arithmetic, so it belongs to no single entity. The use case resolves
each item's captured unit price (via a reader port) and hands the priced items here;
this service does the exact ``Decimal`` maths -- line totals and the order total -- with
no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.order.entities import OrderLine
from src.domain.order.value_objects import Money, OrderQuantity, Sku


@dataclass(frozen=True)
class PricedItem:
    """One item to be ordered, with its unit price already captured from the catalog."""

    sku: Sku
    quantity: OrderQuantity
    unit_price: Money


def build_order_lines(items: Sequence[PricedItem]) -> tuple[OrderLine, ...]:
    """Turn priced items into order lines, computing each line total exactly."""
    return tuple(
        OrderLine(
            sku=item.sku,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.unit_price.times(item.quantity),
        )
        for item in items
    )


def order_total(
    lines: Sequence[OrderLine], currency: str, shipping_cost: Money | None = None
) -> Money:
    """Sum the line totals plus any shipping cost into the grand total.

    Refuses to mix currencies (a shipping cost in another currency is rejected). The
    shipping cost defaults to nothing, so a manual/pre-invoice order (no delivery charge)
    keeps the goods total unchanged.
    """
    total = Money.zero(currency)
    for line in lines:
        total = total.add(line.line_total)
    if shipping_cost is not None:
        total = total.add(shipping_cost)
    return total
