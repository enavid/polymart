"""Use cases (interactors) for the inventory context.

Thin orchestration over the repositories. The atomic, row-locked movement lives in the
repository adapter; these use cases are the application boundary the other contexts
(order checkout, catalog admin/availability) and the inventory admin API depend on,
keeping them decoupled from the inventory infrastructure. Physical on-hand changes are
inventory-sensitive, so the admin use cases emit structured logs *and* a durable
before/after audit entry naming the actor.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.application.audit.ports import AuditRecorder
from src.application.inventory.ports import (
    StockLevelRepository,
    StockPolicyRepository,
    StockSourceRepository,
)
from src.domain.audit.entities import FieldChange
from src.domain.inventory.entities import StockPolicy, StockSource
from src.domain.inventory.value_objects import StockSourceCode

logger = structlog.get_logger(__name__)

# The audited resource is a variant's stock at a single source; the id folds both so the
# trail reads unambiguously (e.g. "HB-250@north"). Actions stay in the "inventory." area.
_RESOURCE_STOCK_LEVEL = "stock_level"
_RESOURCE_STOCK_SOURCE = "stock_source"
_ACTION_STOCK_SET = "inventory.stock_set"
_ACTION_STOCK_ADJUSTED = "inventory.stock_adjusted"
_ACTION_SOURCE_CREATED = "inventory.source_created"
_ACTION_POLICY_SET = "inventory.policy_set"
_RESOURCE_STOCK_POLICY = "stock_policy"


def _level_resource_id(sku: str, source_code: StockSourceCode) -> str:
    return f"{sku}@{source_code.value}"


class ReserveStock:
    """Reserve N units of a variant against available stock (atomic, anti-overselling)."""

    def __init__(self, repository: StockLevelRepository) -> None:
        self._repository = repository

    def execute(self, *, sku: str, quantity: int) -> None:
        self._repository.reserve(sku, quantity)
        logger.info("stock_reserved", sku=sku, quantity=quantity)


class ReleaseReservation:
    """Release N previously reserved units of a variant (atomic)."""

    def __init__(self, repository: StockLevelRepository) -> None:
        self._repository = repository

    def execute(self, *, sku: str, quantity: int) -> None:
        self._repository.release(sku, quantity)
        logger.info("stock_released", sku=sku, quantity=quantity)


class GetAvailability:
    """Return a variant's available-to-promise (on-hand minus reserved, all sources)."""

    def __init__(self, repository: StockLevelRepository) -> None:
        self._repository = repository

    def execute(self, *, sku: str) -> int:
        return self._repository.available_for_skus([sku]).get(sku, 0)


class SetStockOnHand:
    """Set a variant's physical on-hand count at a source to an absolute quantity.

    Setting an absolute value is naturally idempotent. Records a before/after audit entry
    naming the actor (an inventory-sensitive change).
    """

    def __init__(self, repository: StockLevelRepository, audit: AuditRecorder) -> None:
        self._repository = repository
        self._audit = audit

    def execute(
        self, *, sku: str, source_code: StockSourceCode, quantity: int, actor: str | None = None
    ) -> int:
        before = self._repository.on_hand_at(sku, source_code)
        after = self._repository.set_on_hand(sku, source_code, quantity)
        logger.info(
            "stock_on_hand_set", sku=sku, source=source_code.value, quantity=after, actor=actor
        )
        self._audit.record(
            action=_ACTION_STOCK_SET,
            resource_type=_RESOURCE_STOCK_LEVEL,
            resource_id=_level_resource_id(sku, source_code),
            actor=actor,
            changes=(FieldChange(field="on_hand", before=before, after=after),),
        )
        return after


class AdjustStockOnHand:
    """Apply a signed delta to a variant's physical on-hand count at a source.

    The atomic read-modify-write (and the lock serializing concurrent adjustments) lives
    in the repository; the no-below-zero / no-below-reserved rule is enforced there and an
    oversell raises before any write. Records a before/after audit entry naming the actor.
    """

    def __init__(self, repository: StockLevelRepository, audit: AuditRecorder) -> None:
        self._repository = repository
        self._audit = audit

    def execute(
        self, *, sku: str, source_code: StockSourceCode, delta: int, actor: str | None = None
    ) -> int:
        # Derive the before-value from the locked result rather than a second unlocked read:
        # adjust never clamps (it raises), so after == before + delta holds exactly.
        after = self._repository.adjust_on_hand(sku, source_code, delta)
        before = after - delta
        logger.info(
            "stock_on_hand_adjusted", sku=sku, source=source_code.value, delta=delta, actor=actor
        )
        self._audit.record(
            action=_ACTION_STOCK_ADJUSTED,
            resource_type=_RESOURCE_STOCK_LEVEL,
            resource_id=_level_resource_id(sku, source_code),
            actor=actor,
            changes=(FieldChange(field="on_hand", before=before, after=after),),
        )
        return after


@dataclass(frozen=True)
class SourceStock:
    """Read model: a variant's stock at one source (zeros when no level row exists)."""

    sku: str
    source_code: str
    on_hand: int
    reserved: int

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


class GetSourceStock:
    """Read a variant's stock at one source (0/0 if it has never been stocked there)."""

    def __init__(self, repository: StockLevelRepository) -> None:
        self._repository = repository

    def execute(self, *, sku: str, source_code: StockSourceCode) -> SourceStock:
        for level in self._repository.levels_for(sku):
            if level.source_code == source_code:
                return SourceStock(
                    sku=sku,
                    source_code=source_code.value,
                    on_hand=level.on_hand.value,
                    reserved=level.reserved.value,
                )
        return SourceStock(sku=sku, source_code=source_code.value, on_hand=0, reserved=0)


class ListStockSources:
    """List every stock source (warehouse), ordered by code."""

    def __init__(self, sources: StockSourceRepository) -> None:
        self._sources = sources

    def execute(self) -> list[StockSource]:
        return self._sources.list_all()


class GetStockSource:
    """Resolve a stock source by code (raises ``StockSourceNotFoundError`` if unknown).

    Backs the object-scoped permission check: the detail view resolves the source (a 404
    if missing) and hands it to the scope decision before any mutation.
    """

    def __init__(self, sources: StockSourceRepository) -> None:
        self._sources = sources

    def execute(self, *, code: str) -> StockSource:
        return self._sources.get(StockSourceCode(code))


class GetStockPolicy:
    """Read a variant's selling policy (the default if none has been set)."""

    def __init__(self, policies: StockPolicyRepository) -> None:
        self._policies = policies

    def execute(self, *, sku: str) -> StockPolicy:
        return self._policies.get(sku)


@dataclass(frozen=True)
class SetStockPolicyCommand:
    """Input for setting a variant's selling policy (backorder + low-stock threshold)."""

    sku: str
    backorderable: bool
    low_stock_threshold: int


class SetStockPolicy:
    """Create or update a variant's selling policy (backorder flag + low-stock threshold).

    Building the ``StockPolicy`` first fails fast on a malformed threshold (a 400) before
    any I/O. Records an audit entry (an inventory-sensitive configuration change).
    """

    def __init__(self, policies: StockPolicyRepository, audit: AuditRecorder) -> None:
        self._policies = policies
        self._audit = audit

    def execute(self, command: SetStockPolicyCommand, *, actor: str | None = None) -> StockPolicy:
        # Validate through the entity (rejects a negative threshold) before persisting.
        StockPolicy(
            sku=command.sku,
            backorderable=command.backorderable,
            low_stock_threshold=command.low_stock_threshold,
        )
        stored = self._policies.set_policy(
            command.sku,
            backorderable=command.backorderable,
            low_stock_threshold=command.low_stock_threshold,
        )
        logger.info(
            "stock_policy_set",
            sku=command.sku,
            backorderable=stored.backorderable,
            low_stock_threshold=stored.low_stock_threshold,
            actor=actor,
        )
        self._audit.record(
            action=_ACTION_POLICY_SET,
            resource_type=_RESOURCE_STOCK_POLICY,
            resource_id=command.sku,
            actor=actor,
            changes=(
                FieldChange(field="backorderable", after=stored.backorderable),
                FieldChange(field="low_stock_threshold", after=stored.low_stock_threshold),
            ),
        )
        return stored


@dataclass(frozen=True)
class CreateStockSourceCommand:
    """Input for creating a stock source."""

    code: str
    name: str


class CreateStockSource:
    """Create a new stock source (warehouse). A duplicate code is refused.

    Building the ``StockSource`` first fails fast on a malformed code/name (a 400) before
    any I/O; the repository refuses a duplicate code (a 409). Records an audit entry.
    """

    def __init__(self, sources: StockSourceRepository, audit: AuditRecorder) -> None:
        self._sources = sources
        self._audit = audit

    def execute(
        self, command: CreateStockSourceCommand, *, actor: str | None = None
    ) -> StockSource:
        source = StockSource(code=StockSourceCode(command.code), name=command.name)
        stored = self._sources.add(source)
        logger.info("stock_source_created", code=stored.code.value, actor=actor)
        self._audit.record(
            action=_ACTION_SOURCE_CREATED,
            resource_type=_RESOURCE_STOCK_SOURCE,
            resource_id=stored.code.value,
            actor=actor,
            changes=(FieldChange(field="name", after=stored.name),),
        )
        return stored
