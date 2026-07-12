"""Unit tests for inventory domain services: ATP and reservation planning."""

from __future__ import annotations

import pytest

from src.domain.inventory.entities import StockLevel
from src.domain.inventory.exceptions import InsufficientStockError
from src.domain.inventory.services import (
    ReservationLine,
    available_to_promise,
    is_low_stock,
    plan_release,
    plan_reservation,
)
from src.domain.inventory.value_objects import Quantity, StockSourceCode

SKU = "DR-250"


def _level(source: str, on_hand: int, reserved: int = 0) -> StockLevel:
    return StockLevel(
        sku=SKU,
        source_code=StockSourceCode(source),
        on_hand=Quantity(on_hand),
        reserved=Quantity(reserved),
    )


class TestAvailableToPromise:
    def test_sums_available_across_sources(self) -> None:
        levels = [_level("main", 10, 2), _level("tehran-dc", 5, 5)]
        assert available_to_promise(levels) == 8  # (10-2) + (5-5)

    def test_empty_is_zero(self) -> None:
        assert available_to_promise([]) == 0


class TestPlanReservation:
    def test_single_source_exact(self) -> None:
        plan = plan_reservation([_level("main", 5)], sku=SKU, quantity=5)
        assert plan.lines == (ReservationLine(StockSourceCode("main"), 5),)
        assert plan.backordered == 0

    def test_draws_most_available_first(self) -> None:
        levels = [_level("main", 3), _level("tehran-dc", 10)]
        plan = plan_reservation(levels, sku=SKU, quantity=4)
        # tehran-dc has more available, so it is drawn first.
        assert plan.lines == (ReservationLine(StockSourceCode("tehran-dc"), 4),)

    def test_spills_across_sources(self) -> None:
        levels = [_level("main", 3), _level("tehran-dc", 10)]
        plan = plan_reservation(levels, sku=SKU, quantity=12)
        assert plan.lines == (
            ReservationLine(StockSourceCode("tehran-dc"), 10),
            ReservationLine(StockSourceCode("main"), 2),
        )

    def test_tie_broken_by_source_code_deterministically(self) -> None:
        # Equal availability: order by source code so the plan is stable across runs.
        levels = [_level("zeta", 5), _level("alpha", 5)]
        plan = plan_reservation(levels, sku=SKU, quantity=5)
        assert plan.lines == (ReservationLine(StockSourceCode("alpha"), 5),)

    def test_skips_sources_with_no_available(self) -> None:
        levels = [_level("main", 5, 5), _level("tehran-dc", 4)]
        plan = plan_reservation(levels, sku=SKU, quantity=4)
        assert plan.lines == (ReservationLine(StockSourceCode("tehran-dc"), 4),)

    def test_refuses_when_short(self) -> None:
        levels = [_level("main", 2), _level("tehran-dc", 1)]
        with pytest.raises(InsufficientStockError) as exc:
            plan_reservation(levels, sku=SKU, quantity=4)
        assert exc.value.available == 3
        assert exc.value.requested == 4
        assert exc.value.sku == SKU

    def test_refuses_when_available_reduced_by_reservations(self) -> None:
        # 10 on hand but 9 already reserved -> only 1 available.
        with pytest.raises(InsufficientStockError):
            plan_reservation([_level("main", 10, 9)], sku=SKU, quantity=2)

    @pytest.mark.parametrize("bad_qty", [0, -1])
    def test_rejects_non_positive_quantity(self, bad_qty: int) -> None:
        with pytest.raises(InsufficientStockError):
            plan_reservation([_level("main", 5)], sku=SKU, quantity=bad_qty)


class TestPlanReservationBackorder:
    def test_backorderable_reserves_physical_and_records_the_shortfall(self) -> None:
        # 3 available, want 5 -> reserve the 3 physical, backorder the remaining 2.
        plan = plan_reservation([_level("main", 3)], sku=SKU, quantity=5, backorderable=True)
        assert plan.lines == (ReservationLine(StockSourceCode("main"), 3),)
        assert plan.backordered == 2

    def test_backorderable_with_no_stock_is_all_backorder(self) -> None:
        plan = plan_reservation([_level("main", 5, 5)], sku=SKU, quantity=4, backorderable=True)
        assert plan.lines == ()
        assert plan.backordered == 4

    def test_backorderable_within_stock_does_not_backorder(self) -> None:
        plan = plan_reservation([_level("main", 5)], sku=SKU, quantity=2, backorderable=True)
        assert plan.lines == (ReservationLine(StockSourceCode("main"), 2),)
        assert plan.backordered == 0


class TestPlanRelease:
    def test_single_source(self) -> None:
        plan = plan_release([_level("main", 10, 4)], sku=SKU, quantity=3)
        assert plan == [ReservationLine(StockSourceCode("main"), 3)]

    def test_draws_most_reserved_first(self) -> None:
        levels = [_level("main", 10, 2), _level("tehran-dc", 10, 7)]
        plan = plan_release(levels, sku=SKU, quantity=5)
        assert plan == [ReservationLine(StockSourceCode("tehran-dc"), 5)]

    def test_spills_across_sources(self) -> None:
        levels = [_level("main", 10, 2), _level("tehran-dc", 10, 7)]
        plan = plan_release(levels, sku=SKU, quantity=8)
        assert plan == [
            ReservationLine(StockSourceCode("tehran-dc"), 7),
            ReservationLine(StockSourceCode("main"), 1),
        ]

    def test_tie_broken_by_source_code(self) -> None:
        levels = [_level("zeta", 10, 5), _level("alpha", 10, 5)]
        plan = plan_release(levels, sku=SKU, quantity=5)
        assert plan == [ReservationLine(StockSourceCode("alpha"), 5)]

    def test_refuses_releasing_more_than_reserved(self) -> None:
        with pytest.raises(InsufficientStockError):
            plan_release([_level("main", 10, 3)], sku=SKU, quantity=4)

    @pytest.mark.parametrize("bad_qty", [0, -2])
    def test_rejects_non_positive(self, bad_qty: int) -> None:
        with pytest.raises(InsufficientStockError):
            plan_release([_level("main", 10, 5)], sku=SKU, quantity=bad_qty)


class TestIsLowStock:
    def test_below_threshold_is_low(self) -> None:
        assert is_low_stock(available=2, threshold=5) is True

    def test_at_threshold_is_low(self) -> None:
        # "at or below" -- reaching the threshold is the trigger point.
        assert is_low_stock(available=5, threshold=5) is True

    def test_above_threshold_is_not_low(self) -> None:
        assert is_low_stock(available=6, threshold=5) is False

    def test_zero_threshold_disables_the_alert(self) -> None:
        # A threshold of 0 means "not tracked": even 0 available does not alert.
        assert is_low_stock(available=0, threshold=0) is False
