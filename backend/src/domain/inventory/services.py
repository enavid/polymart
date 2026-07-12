"""Domain services for the inventory context.

Pure functions over stock levels: computing a variant's available-to-promise, and
planning how a reservation is drawn from the available sources. The overselling guard
lives here -- a reservation that exceeds available-to-promise is refused before any
movement, so no adapter can partially apply an impossible reservation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.inventory.entities import StockLevel
from src.domain.inventory.exceptions import InsufficientStockError
from src.domain.inventory.value_objects import StockSourceCode


@dataclass(frozen=True)
class ReservationLine:
    """One step of a reservation plan: reserve ``quantity`` at ``source_code``."""

    source_code: StockSourceCode
    quantity: int


@dataclass(frozen=True)
class ReservationPlan:
    """How a reservation is satisfied: physical reservations, plus any backorder overflow.

    ``lines`` reserve against physical available stock per source (each keeps
    ``reserved <= on_hand``); ``backordered`` is the remainder promised beyond physical
    stock -- non-zero only for a backorderable variant that is short.
    """

    lines: tuple[ReservationLine, ...]
    backordered: int = 0


def available_to_promise(levels: Sequence[StockLevel]) -> int:
    """Sum the sellable (available) units across a variant's stock levels."""
    return sum(level.available for level in levels)


def is_low_stock(available: int, threshold: int) -> bool:
    """Whether available-to-promise has fallen to or below the low-stock threshold.

    A threshold of 0 disables the alert (there is no meaningful "low" for an untracked
    variant), so only a positive threshold can trigger it.
    """
    return threshold > 0 and available <= threshold


def plan_reservation(
    levels: Sequence[StockLevel], *, sku: str, quantity: int, backorderable: bool = False
) -> ReservationPlan:
    """Plan how to reserve ``quantity`` units of ``sku`` across its stock levels.

    Draws from the source with the most available first (deterministic on ties by source
    code, so the plan is stable). When available-to-promise is short: a non-backorderable
    variant is refused whole with ``InsufficientStockError`` (never a partial plan); a
    backorderable variant reserves all physical stock and records the shortfall as
    ``backordered`` (a promise with no physical backing).
    """
    if quantity <= 0:
        raise InsufficientStockError(
            sku=sku, requested=quantity, available=available_to_promise(levels)
        )
    total_available = available_to_promise(levels)
    if quantity > total_available and not backorderable:
        raise InsufficientStockError(sku=sku, requested=quantity, available=total_available)

    # Reserve against physical stock up to what is available; any remainder is backorder.
    physical = min(quantity, total_available)
    # Most-available-first, tie-broken by source code for a stable, deterministic plan.
    ordered = sorted(
        (level for level in levels if level.available > 0),
        key=lambda level: (-level.available, level.source_code.value),
    )
    lines: list[ReservationLine] = []
    remaining = physical
    for level in ordered:
        if remaining == 0:
            break
        take = min(level.available, remaining)
        lines.append(ReservationLine(source_code=level.source_code, quantity=take))
        remaining -= take
    return ReservationPlan(lines=tuple(lines), backordered=quantity - physical)


def plan_release(levels: Sequence[StockLevel], *, sku: str, quantity: int) -> list[ReservationLine]:
    """Plan how to release ``quantity`` reserved units of ``sku`` across its levels.

    Draws from the source with the most reserved first (deterministic on ties by source
    code). Refuses with ``InsufficientStockError`` if fewer than ``quantity`` units are
    reserved in total -- a caller can never release more than is held.
    """
    if quantity <= 0:
        raise InsufficientStockError(sku=sku, requested=quantity, available=0)
    total_reserved = sum(level.reserved.value for level in levels)
    if quantity > total_reserved:
        raise InsufficientStockError(sku=sku, requested=quantity, available=total_reserved)

    ordered = sorted(
        (level for level in levels if level.reserved.value > 0),
        key=lambda level: (-level.reserved.value, level.source_code.value),
    )
    plan: list[ReservationLine] = []
    remaining = quantity
    for level in ordered:
        if remaining == 0:
            break
        take = min(level.reserved.value, remaining)
        plan.append(ReservationLine(source_code=level.source_code, quantity=take))
        remaining -= take
    return plan
