"""Unit tests for the variant stock use cases (fakes, no DB)."""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import StockRepository, VariantRepository
from src.application.catalog.use_cases import (
    AdjustVariantStock,
    AdjustVariantStockCommand,
    GetVariantStock,
    SetVariantStock,
    SetVariantStockCommand,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import ProductVariant
from src.domain.catalog.exceptions import (
    InsufficientStockError,
    InvalidStockQuantityError,
    VariantNotFoundError,
)
from src.domain.catalog.services import adjust_stock
from src.domain.catalog.value_objects import ProductCode, Sku, StockQuantity


class FakeVariantRepository(VariantRepository):
    def __init__(self) -> None:
        self._by_sku: dict[str, ProductVariant] = {}

    def seed(self, variant: ProductVariant) -> None:
        variant.id = len(self._by_sku) + 1
        self._by_sku[variant.sku.value] = variant

    def add(self, variant: ProductVariant) -> ProductVariant:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_sku(self, sku: str) -> ProductVariant:
        try:
            return self._by_sku[sku]
        except KeyError:
            raise VariantNotFoundError(sku) from None

    def exists_by_sku(self, sku: str) -> bool:  # pragma: no cover - unused here
        return sku in self._by_sku

    def list_for_product(self, product_code: str) -> list[ProductVariant]:  # pragma: no cover
        raise NotImplementedError


class FakeStockRepository(StockRepository):
    """In-memory stock that mirrors the real adapter (adjust uses the domain rule)."""

    def __init__(self) -> None:
        self._by_sku: dict[str, StockQuantity] = {}

    def get_quantity(self, sku: str) -> StockQuantity:
        return self._by_sku.get(sku, StockQuantity(0))

    def set_quantity(self, sku: str, quantity: StockQuantity) -> StockQuantity:
        self._by_sku[sku] = quantity
        return quantity

    def adjust_quantity(self, sku: str, delta: int) -> StockQuantity:
        new_quantity = adjust_stock(self._by_sku.get(sku, StockQuantity(0)), delta)
        self._by_sku[sku] = new_quantity
        return new_quantity


class RecordingAudit(AuditRecorder):
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None,
        changes: tuple[FieldChange, ...],
    ) -> None:
        self.records.append(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "actor": actor,
                "changes": changes,
            }
        )


def _variant(sku: str = "HB-250") -> ProductVariant:
    return ProductVariant(product=ProductCode("house-blend"), sku=Sku(sku), name="House Blend 250g")


@pytest.fixture
def variants() -> FakeVariantRepository:
    repo = FakeVariantRepository()
    repo.seed(_variant())
    return repo


@pytest.fixture
def stock() -> FakeStockRepository:
    return FakeStockRepository()


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


class TestSetVariantStock:
    def test_sets_the_quantity(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        use_case = SetVariantStock(stock, variants, audit)

        result = use_case.execute(SetVariantStockCommand(variant="HB-250", quantity=12))

        assert result == StockQuantity(12)
        assert stock.get_quantity("HB-250") == StockQuantity(12)

    def test_setting_is_idempotent(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        use_case = SetVariantStock(stock, variants, audit)
        use_case.execute(SetVariantStockCommand(variant="HB-250", quantity=12))

        result = use_case.execute(SetVariantStockCommand(variant="HB-250", quantity=12))

        assert result == StockQuantity(12)

    def test_records_a_stock_sensitive_audit_event_with_before_and_after(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        use_case = SetVariantStock(stock, variants, audit)
        use_case.execute(SetVariantStockCommand(variant="HB-250", quantity=10))

        use_case.execute(SetVariantStockCommand(variant="HB-250", quantity=4), actor="42")

        record = audit.records[-1]
        assert record["action"] == "variant.stock_changed"
        assert record["resource_type"] == "variant"
        assert record["actor"] == "42"
        change = record["changes"][0]
        assert change.field == "quantity"
        assert change.before == 10
        assert change.after == 4

    def test_logs_a_structured_event_with_the_actor(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        use_case = SetVariantStock(stock, variants, audit)

        with capture_logs() as logs:
            use_case.execute(SetVariantStockCommand(variant="HB-250", quantity=12), actor="42")

        events = [e for e in logs if e["event"] == "variant_stock_set"]
        assert events and events[0]["actor"] == "42" and events[0]["quantity"] == 12

    def test_unknown_variant_raises_not_found(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        use_case = SetVariantStock(stock, variants, audit)

        with pytest.raises(VariantNotFoundError):
            use_case.execute(SetVariantStockCommand(variant="GHOST", quantity=12))

    def test_rejects_a_negative_quantity(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        use_case = SetVariantStock(stock, variants, audit)

        with pytest.raises(InvalidStockQuantityError):
            use_case.execute(SetVariantStockCommand(variant="HB-250", quantity=-1))

        assert audit.records == []


class TestAdjustVariantStock:
    def test_a_positive_delta_increases_the_quantity(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        SetVariantStock(stock, variants, audit).execute(
            SetVariantStockCommand(variant="HB-250", quantity=10)
        )
        use_case = AdjustVariantStock(stock, variants, audit)

        result = use_case.execute(AdjustVariantStockCommand(variant="HB-250", delta=5))

        assert result == StockQuantity(15)

    def test_a_negative_delta_decreases_the_quantity(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        SetVariantStock(stock, variants, audit).execute(
            SetVariantStockCommand(variant="HB-250", quantity=10)
        )
        use_case = AdjustVariantStock(stock, variants, audit)

        result = use_case.execute(AdjustVariantStockCommand(variant="HB-250", delta=-4))

        assert result == StockQuantity(6)

    def test_adjusting_from_no_stock_starts_at_zero(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        use_case = AdjustVariantStock(stock, variants, audit)

        result = use_case.execute(AdjustVariantStockCommand(variant="HB-250", delta=3))

        assert result == StockQuantity(3)

    def test_records_a_stock_sensitive_audit_event(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        SetVariantStock(stock, variants, audit).execute(
            SetVariantStockCommand(variant="HB-250", quantity=10)
        )
        AdjustVariantStock(stock, variants, audit).execute(
            AdjustVariantStockCommand(variant="HB-250", delta=-3), actor="42"
        )

        record = audit.records[-1]
        assert record["action"] == "variant.stock_changed"
        assert record["actor"] == "42"
        change = record["changes"][0]
        assert change.before == 10
        assert change.after == 7

    def test_logs_a_structured_event_with_delta_and_quantity(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        SetVariantStock(stock, variants, audit).execute(
            SetVariantStockCommand(variant="HB-250", quantity=10)
        )

        with capture_logs() as logs:
            AdjustVariantStock(stock, variants, audit).execute(
                AdjustVariantStockCommand(variant="HB-250", delta=-3), actor="42"
            )

        events = [e for e in logs if e["event"] == "variant_stock_adjusted"]
        assert events and events[0]["delta"] == -3 and events[0]["quantity"] == 7

    def test_an_oversell_is_rejected_and_does_not_persist_or_audit(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        SetVariantStock(stock, variants, audit).execute(
            SetVariantStockCommand(variant="HB-250", quantity=2)
        )
        audit.records.clear()
        use_case = AdjustVariantStock(stock, variants, audit)

        with pytest.raises(InsufficientStockError):
            use_case.execute(AdjustVariantStockCommand(variant="HB-250", delta=-3))

        assert stock.get_quantity("HB-250") == StockQuantity(2)
        assert audit.records == []

    def test_unknown_variant_raises_not_found(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        use_case = AdjustVariantStock(stock, variants, audit)

        with pytest.raises(VariantNotFoundError):
            use_case.execute(AdjustVariantStockCommand(variant="GHOST", delta=1))


class TestGetVariantStock:
    def test_returns_the_quantity(
        self, stock: FakeStockRepository, variants: FakeVariantRepository, audit: RecordingAudit
    ) -> None:
        SetVariantStock(stock, variants, audit).execute(
            SetVariantStockCommand(variant="HB-250", quantity=9)
        )

        assert GetVariantStock(stock, variants).execute(sku="HB-250") == StockQuantity(9)

    def test_defaults_to_zero_for_a_variant_without_a_stock_record(
        self, stock: FakeStockRepository, variants: FakeVariantRepository
    ) -> None:
        assert GetVariantStock(stock, variants).execute(sku="HB-250") == StockQuantity(0)

    def test_unknown_variant_raises_not_found(
        self, stock: FakeStockRepository, variants: FakeVariantRepository
    ) -> None:
        with pytest.raises(VariantNotFoundError):
            GetVariantStock(stock, variants).execute(sku="GHOST")
