"""Django ORM adapters for the inventory context.

Every stock movement (reserve, release, physical set/adjust) runs its whole
read-modify-write inside ``transaction.atomic()`` under a row lock on the affected
stock-level rows, so two concurrent reservations on the last unit serialize instead of
racing -- the anti-overselling guarantee. The domain services do the planning; the
adapter only locks, applies the plan, and persists.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog
from django.db import transaction
from django.db.models import F, Sum

from src.application.inventory.ports import (
    StockLevelRepository,
    StockPolicyRepository,
    StockSourceRepository,
)
from src.domain.inventory.entities import StockLevel, StockPolicy, StockSource
from src.domain.inventory.exceptions import (
    InsufficientStockError,
    StockSourceAlreadyExistsError,
    StockSourceNotFoundError,
)
from src.domain.inventory.services import is_low_stock, plan_release, plan_reservation
from src.domain.inventory.value_objects import Quantity, StockSourceCode
from src.infrastructure.inventory.models import (
    StockLevelModel,
    StockPolicyModel,
    StockSourceModel,
)

logger = structlog.get_logger(__name__)

# The default single source every store starts with; the existing single-count stock is
# migrated into it, and contexts that do not (yet) choose a source operate on it.
DEFAULT_STOCK_SOURCE_CODE = "main"
DEFAULT_STOCK_SOURCE_NAME = "Main"


class DjangoStockSourceRepository(StockSourceRepository):
    """Persist stock sources with the Django ORM."""

    def ensure_default(self) -> StockSourceCode:
        StockSourceModel.objects.get_or_create(
            code=DEFAULT_STOCK_SOURCE_CODE,
            defaults={"name": DEFAULT_STOCK_SOURCE_NAME},
        )
        return StockSourceCode(DEFAULT_STOCK_SOURCE_CODE)

    def exists(self, code: StockSourceCode) -> bool:
        return StockSourceModel.objects.filter(code=code.value).exists()

    def add(self, source: StockSource) -> StockSource:
        if self.exists(source.code):
            raise StockSourceAlreadyExistsError(source.code.value)
        row = StockSourceModel.objects.create(code=source.code.value, name=source.name)
        return self._to_domain(row)

    def list_all(self) -> list[StockSource]:
        rows = StockSourceModel.objects.order_by("code")
        return [self._to_domain(row) for row in rows]

    def get(self, code: StockSourceCode) -> StockSource:
        try:
            row = StockSourceModel.objects.get(code=code.value)
        except StockSourceModel.DoesNotExist as exc:
            raise StockSourceNotFoundError(code.value) from exc
        return self._to_domain(row)

    @staticmethod
    def _to_domain(row: StockSourceModel) -> StockSource:
        return StockSource(code=StockSourceCode(row.code), name=row.name, id=row.pk)


class DjangoStockLevelRepository(StockLevelRepository):
    """Persist per-source stock levels; all mutations are atomic and row-locked."""

    def __init__(self) -> None:
        self._sources = DjangoStockSourceRepository()

    def levels_for(self, sku: str) -> list[StockLevel]:
        rows = StockLevelModel.objects.filter(sku=sku).select_related("source")
        return [self._to_domain(row) for row in rows]

    def reserve(self, sku: str, quantity: int) -> None:
        with transaction.atomic():
            rows = self._lock_levels(sku)
            policy = self._lock_policy(sku)
            plan = plan_reservation(
                [self._to_domain(row) for row in rows],
                sku=sku,
                quantity=quantity,
                backorderable=policy.backorderable,
            )
            by_code = {row.source.code: row for row in rows}
            for line in plan.lines:
                row = by_code[line.source_code.value]
                row.reserved = F("reserved") + line.quantity
                row.save(update_fields=["reserved", "updated_at"])
            if plan.backordered:
                # The overflow has no physical backing: track it on the policy so the
                # per-source ``reserved <= on_hand`` invariant is never violated.
                policy.backordered = F("backordered") + plan.backordered
                policy.save(update_fields=["backordered", "updated_at"])
                logger.info("stock_backordered", sku=sku, quantity=plan.backordered)
            self._alert_if_low(sku, policy.low_stock_threshold)

    def release(self, sku: str, quantity: int) -> None:
        with transaction.atomic():
            rows = self._lock_levels(sku)
            policy = self._lock_policy(sku)
            # Free any backorder promise first (it was reserved last), then physical stock.
            from_backorder = min(quantity, policy.backordered)
            if from_backorder:
                policy.backordered = F("backordered") - from_backorder
                policy.save(update_fields=["backordered", "updated_at"])
            physical = quantity - from_backorder
            if physical:
                plan = plan_release(
                    [self._to_domain(row) for row in rows], sku=sku, quantity=physical
                )
                by_code = {row.source.code: row for row in rows}
                for line in plan:
                    row = by_code[line.source_code.value]
                    row.reserved = F("reserved") - line.quantity
                    row.save(update_fields=["reserved", "updated_at"])

    def set_on_hand(self, sku: str, source_code: StockSourceCode, quantity: int) -> int:
        with transaction.atomic():
            row = self._lock_level_row(sku, source_code)
            if quantity < row.reserved:
                # The physical count can never drop below what is already reserved.
                raise InsufficientStockError(
                    sku=sku, requested=row.reserved - quantity, available=row.reserved
                )
            row.on_hand = quantity
            row.save(update_fields=["on_hand", "updated_at"])
            self._alert_if_low(sku, self._threshold(sku))
            return quantity

    def adjust_on_hand(self, sku: str, source_code: StockSourceCode, delta: int) -> int:
        with transaction.atomic():
            row = self._lock_level_row(sku, source_code)
            new_on_hand = row.on_hand + delta
            if new_on_hand < 0 or new_on_hand < row.reserved:
                raise InsufficientStockError(
                    sku=sku, requested=-delta, available=row.on_hand - row.reserved
                )
            row.on_hand = new_on_hand
            row.save(update_fields=["on_hand", "updated_at"])
            self._alert_if_low(sku, self._threshold(sku))
            return new_on_hand

    def on_hand_at(self, sku: str, source_code: StockSourceCode) -> int:
        row = (
            StockLevelModel.objects.filter(sku=sku, source__code=source_code.value)
            .values_list("on_hand", flat=True)
            .first()
        )
        return int(row or 0)

    def total_on_hand(self, sku: str) -> int:
        total = StockLevelModel.objects.filter(sku=sku).aggregate(total=Sum("on_hand"))["total"]
        return int(total or 0)

    def available_for_skus(self, skus: Sequence[str]) -> dict[str, int]:
        if not skus:
            return {}
        rows = (
            StockLevelModel.objects.filter(sku__in=list(skus))
            .values("sku")
            .annotate(on_hand=Sum("on_hand"), reserved=Sum("reserved"))
        )
        return {row["sku"]: int(row["on_hand"]) - int(row["reserved"]) for row in rows}

    def _lock_levels(self, sku: str) -> list[StockLevelModel]:
        return list(
            StockLevelModel.objects.select_for_update().filter(sku=sku).select_related("source")
        )

    def _lock_policy(self, sku: str) -> StockPolicyModel:
        """Get-or-create then lock the sku's policy row for the read-modify-write."""
        StockPolicyModel.objects.get_or_create(sku=sku)
        return StockPolicyModel.objects.select_for_update().get(sku=sku)

    def _threshold(self, sku: str) -> int:
        row = (
            StockPolicyModel.objects.filter(sku=sku)
            .values_list("low_stock_threshold", flat=True)
            .first()
        )
        return int(row or 0)

    def _alert_if_low(self, sku: str, threshold: int) -> None:
        """Emit a structured low-stock alert if available-to-promise is at/below threshold."""
        available = self.available_for_skus([sku]).get(sku, 0)
        if is_low_stock(available, threshold):
            logger.warning("stock_low", sku=sku, available=available, threshold=threshold)

    def _lock_level_row(self, sku: str, source_code: StockSourceCode) -> StockLevelModel:
        source = self._get_source(source_code)
        # Ensure the row exists, then take the lock on it for the read-modify-write.
        StockLevelModel.objects.get_or_create(sku=sku, source=source)
        return StockLevelModel.objects.select_for_update().get(sku=sku, source=source)

    def _get_source(self, source_code: StockSourceCode) -> StockSourceModel:
        try:
            return StockSourceModel.objects.get(code=source_code.value)
        except StockSourceModel.DoesNotExist as exc:
            raise StockSourceNotFoundError(source_code.value) from exc

    @staticmethod
    def _to_domain(row: StockLevelModel) -> StockLevel:
        return StockLevel(
            sku=row.sku,
            source_code=StockSourceCode(row.source.code),
            on_hand=Quantity(row.on_hand),
            reserved=Quantity(row.reserved),
        )


class DjangoStockPolicyRepository(StockPolicyRepository):
    """Persist per-variant selling policy (backorder + low-stock threshold)."""

    def get(self, sku: str) -> StockPolicy:
        row = StockPolicyModel.objects.filter(sku=sku).first()
        if row is None:
            return StockPolicy(sku=sku)
        return self._to_domain(row)

    def set_policy(self, sku: str, *, backorderable: bool, low_stock_threshold: int) -> StockPolicy:
        # Upsert without touching ``backordered`` -- that is movement state, not config.
        row, _ = StockPolicyModel.objects.update_or_create(
            sku=sku,
            defaults={"backorderable": backorderable, "low_stock_threshold": low_stock_threshold},
        )
        return self._to_domain(row)

    def backorderable_skus(self, skus: Sequence[str]) -> set[str]:
        if not skus:
            return set()
        return set(
            StockPolicyModel.objects.filter(sku__in=list(skus), backorderable=True).values_list(
                "sku", flat=True
            )
        )

    @staticmethod
    def _to_domain(row: StockPolicyModel) -> StockPolicy:
        return StockPolicy(
            sku=row.sku,
            backorderable=row.backorderable,
            low_stock_threshold=row.low_stock_threshold,
            backordered=Quantity(row.backordered),
        )
