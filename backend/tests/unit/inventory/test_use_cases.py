"""Unit tests for inventory use cases against fake repositories (no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from src.application.inventory.ports import StockLevelRepository, StockSourceRepository
from src.application.inventory.use_cases import (
    AdjustStockOnHand,
    CreateStockSource,
    CreateStockSourceCommand,
    GetAvailability,
    GetSourceStock,
    ListStockSources,
    ReleaseReservation,
    ReserveStock,
    SetStockOnHand,
)
from src.domain.audit.entities import FieldChange
from src.domain.inventory.entities import StockLevel, StockSource
from src.domain.inventory.exceptions import (
    InsufficientStockError,
    StockSourceAlreadyExistsError,
    StockSourceNotFoundError,
)
from src.domain.inventory.services import plan_release, plan_reservation
from src.domain.inventory.value_objects import Quantity, StockSourceCode

SKU = "DR-250"
MAIN = StockSourceCode("main")


@dataclass
class _RecordedAudit:
    action: str
    resource_type: str
    resource_id: str
    actor: str | None
    changes: tuple[FieldChange, ...]


class FakeAuditRecorder:
    """Capture recorded calls so tests can assert the before/after audit trail."""

    def __init__(self) -> None:
        self.entries: list[_RecordedAudit] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: Sequence[FieldChange] = (),
    ) -> None:
        self.entries.append(
            _RecordedAudit(action, resource_type, resource_id, actor, tuple(changes))
        )


class FakeStockLevelRepository(StockLevelRepository):
    """In-memory single-source stock, applying the same domain planning as the real repo."""

    def __init__(self, *, on_hand: int = 0, reserved: int = 0) -> None:
        self._on_hand = on_hand
        self._reserved = reserved

    def _levels(self) -> list[StockLevel]:
        return [
            StockLevel(
                sku=SKU,
                source_code=MAIN,
                on_hand=Quantity(self._on_hand),
                reserved=Quantity(self._reserved),
            )
        ]

    def levels_for(self, sku: str) -> list[StockLevel]:
        return self._levels()

    def reserve(self, sku: str, quantity: int) -> None:
        plan = plan_reservation(self._levels(), sku=sku, quantity=quantity)
        self._reserved += sum(line.quantity for line in plan.lines)

    def release(self, sku: str, quantity: int) -> None:
        plan = plan_release(self._levels(), sku=sku, quantity=quantity)
        self._reserved -= sum(line.quantity for line in plan)

    def set_on_hand(self, sku: str, source_code: StockSourceCode, quantity: int) -> int:
        self._on_hand = quantity
        return self._on_hand

    def adjust_on_hand(self, sku: str, source_code: StockSourceCode, delta: int) -> int:
        self._on_hand += delta
        return self._on_hand

    def on_hand_at(self, sku: str, source_code: StockSourceCode) -> int:
        return self._on_hand

    def total_on_hand(self, sku: str) -> int:
        return self._on_hand

    def available_for_skus(self, skus: Sequence[str]) -> dict[str, int]:
        return {SKU: self._on_hand - self._reserved}


class FakeStockSourceRepository(StockSourceRepository):
    """In-memory stock sources, assigning ids on insert like the real repo."""

    def __init__(self) -> None:
        self._sources: dict[str, StockSource] = {}
        self._next_id = 1

    def ensure_default(self) -> StockSourceCode:
        raise NotImplementedError

    def exists(self, code: StockSourceCode) -> bool:
        return code.value in self._sources

    def add(self, source: StockSource) -> StockSource:
        if source.code.value in self._sources:
            raise StockSourceAlreadyExistsError(source.code.value)
        stored = StockSource(code=source.code, name=source.name, id=self._next_id)
        self._sources[source.code.value] = stored
        self._next_id += 1
        return stored

    def list_all(self) -> list[StockSource]:
        return [self._sources[code] for code in sorted(self._sources)]

    def get(self, code: StockSourceCode) -> StockSource:
        try:
            return self._sources[code.value]
        except KeyError:
            raise StockSourceNotFoundError(code.value) from None


class TestReserveAndRelease:
    def test_reserve_reduces_availability(self) -> None:
        repo = FakeStockLevelRepository(on_hand=5)
        ReserveStock(repo).execute(sku=SKU, quantity=2)
        assert GetAvailability(repo).execute(sku=SKU) == 3

    def test_reserve_refuses_overselling(self) -> None:
        repo = FakeStockLevelRepository(on_hand=1)
        with pytest.raises(InsufficientStockError):
            ReserveStock(repo).execute(sku=SKU, quantity=2)
        # No partial movement: availability is untouched.
        assert GetAvailability(repo).execute(sku=SKU) == 1

    def test_release_restores_availability(self) -> None:
        repo = FakeStockLevelRepository(on_hand=5, reserved=3)
        ReleaseReservation(repo).execute(sku=SKU, quantity=2)
        assert GetAvailability(repo).execute(sku=SKU) == 4  # 5 - (3-2)

    def test_reserve_then_release_round_trips(self) -> None:
        repo = FakeStockLevelRepository(on_hand=5)
        ReserveStock(repo).execute(sku=SKU, quantity=5)
        assert GetAvailability(repo).execute(sku=SKU) == 0
        ReleaseReservation(repo).execute(sku=SKU, quantity=5)
        assert GetAvailability(repo).execute(sku=SKU) == 5


class TestPhysicalOnHand:
    def test_set_on_hand_returns_and_audits_before_after(self) -> None:
        repo = FakeStockLevelRepository(on_hand=12)
        audit = FakeAuditRecorder()

        result = SetStockOnHand(repo, audit).execute(
            sku=SKU, source_code=MAIN, quantity=30, actor="admin"
        )

        assert result == 30
        assert repo.total_on_hand(SKU) == 30
        (entry,) = audit.entries
        assert entry.action == "inventory.stock_set"
        assert entry.resource_id == f"{SKU}@main"
        assert entry.changes[0].before == 12
        assert entry.changes[0].after == 30

    def test_adjust_on_hand_audits_derived_before(self) -> None:
        repo = FakeStockLevelRepository(on_hand=10)
        audit = FakeAuditRecorder()

        result = AdjustStockOnHand(repo, audit).execute(
            sku=SKU, source_code=MAIN, delta=-4, actor="admin"
        )

        assert result == 6
        assert repo.total_on_hand(SKU) == 6
        (entry,) = audit.entries
        assert entry.action == "inventory.stock_adjusted"
        assert entry.changes[0].before == 10
        assert entry.changes[0].after == 6


class TestGetSourceStock:
    def test_reads_the_level_at_a_source(self) -> None:
        repo = FakeStockLevelRepository(on_hand=5, reserved=2)
        result = GetSourceStock(repo).execute(sku=SKU, source_code=MAIN)
        assert (result.on_hand, result.reserved, result.available) == (5, 2, 3)

    def test_an_unstocked_source_reads_as_zero(self) -> None:
        repo = FakeStockLevelRepository(on_hand=5)
        result = GetSourceStock(repo).execute(sku=SKU, source_code=StockSourceCode("north"))
        assert (result.on_hand, result.reserved, result.available) == (0, 0, 0)


class TestStockSources:
    def test_create_assigns_an_id_and_audits(self) -> None:
        sources = FakeStockSourceRepository()
        audit = FakeAuditRecorder()

        created = CreateStockSource(sources, audit).execute(
            CreateStockSourceCommand(code="north", name="North Warehouse"), actor="admin"
        )

        assert created.id == 1
        assert created.code == StockSourceCode("north")
        (entry,) = audit.entries
        assert entry.action == "inventory.source_created"
        assert entry.resource_id == "north"

    def test_create_refuses_a_duplicate_code(self) -> None:
        sources = FakeStockSourceRepository()
        audit = FakeAuditRecorder()
        CreateStockSource(sources, audit).execute(
            CreateStockSourceCommand(code="north", name="North")
        )

        with pytest.raises(StockSourceAlreadyExistsError):
            CreateStockSource(sources, audit).execute(
                CreateStockSourceCommand(code="north", name="North Again")
            )

    def test_list_returns_sources_by_code(self) -> None:
        sources = FakeStockSourceRepository()
        audit = FakeAuditRecorder()
        CreateStockSource(sources, audit).execute(CreateStockSourceCommand(code="south", name="S"))
        CreateStockSource(sources, audit).execute(CreateStockSourceCommand(code="north", name="N"))

        listed = ListStockSources(sources).execute()

        assert [s.code.value for s in listed] == ["north", "south"]
