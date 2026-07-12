"""Integration tests for the Django inventory repositories (real DB).

These prove the source-of-truth stock model: per-source levels round-trip, reservations
lower available-to-promise without touching physical on-hand, planning spills across
sources most-available-first, and the physical-count guards (never below what is reserved,
never negative) hold. The database ``CheckConstraint`` is the backstop asserted here, and
the anti-overselling guarantee is exercised as the last-unit double-reserve refusal.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from django.db.models import F
from structlog.testing import capture_logs

from src.domain.inventory.entities import StockSource
from src.domain.inventory.exceptions import (
    InsufficientStockError,
    StockSourceAlreadyExistsError,
    StockSourceNotFoundError,
)
from src.domain.inventory.value_objects import StockSourceCode
from src.infrastructure.inventory.models import (
    StockLevelModel,
    StockPolicyModel,
    StockSourceModel,
)
from src.infrastructure.inventory.repositories import (
    DEFAULT_STOCK_SOURCE_CODE,
    DjangoStockLevelRepository,
    DjangoStockPolicyRepository,
    DjangoStockSourceRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _source(code: str, name: str | None = None) -> StockSourceModel:
    # The default "main" source is seeded into every DB by the inventory data migration,
    # so create-or-get keeps the helper usable for both the default and extra sources.
    source, _ = StockSourceModel.objects.get_or_create(
        code=code, defaults={"name": name or code.title()}
    )
    return source


def _level(sku: str, source: StockSourceModel, *, on_hand: int, reserved: int = 0) -> None:
    StockLevelModel.objects.create(sku=sku, source=source, on_hand=on_hand, reserved=reserved)


class TestStockSourceRepository:
    def test_ensure_default_creates_the_main_source_and_is_idempotent(self) -> None:
        repo = DjangoStockSourceRepository()

        first = repo.ensure_default()
        second = repo.ensure_default()

        assert first == StockSourceCode(DEFAULT_STOCK_SOURCE_CODE) == second
        assert StockSourceModel.objects.filter(code=DEFAULT_STOCK_SOURCE_CODE).count() == 1

    def test_exists_reflects_persistence(self) -> None:
        repo = DjangoStockSourceRepository()
        assert repo.exists(StockSourceCode("warehouse-north")) is False

        _source("warehouse-north")

        assert repo.exists(StockSourceCode("warehouse-north")) is True

    def test_add_persists_and_assigns_an_id(self) -> None:
        repo = DjangoStockSourceRepository()

        created = repo.add(StockSource(code=StockSourceCode("north"), name="North Warehouse"))

        assert created.id is not None
        assert repo.get(StockSourceCode("north")).name == "North Warehouse"

    def test_add_refuses_a_duplicate_code(self) -> None:
        repo = DjangoStockSourceRepository()
        repo.add(StockSource(code=StockSourceCode("north"), name="North"))

        with pytest.raises(StockSourceAlreadyExistsError):
            repo.add(StockSource(code=StockSourceCode("north"), name="North Again"))

    def test_list_all_is_ordered_by_code_including_the_seeded_default(self) -> None:
        repo = DjangoStockSourceRepository()
        repo.add(StockSource(code=StockSourceCode("south"), name="S"))
        repo.add(StockSource(code=StockSourceCode("north"), name="N"))

        codes = [s.code.value for s in repo.list_all()]

        # "main" is seeded by the data migration; the new sources sort in by code.
        assert codes == ["main", "north", "south"]

    def test_get_raises_for_an_unknown_code(self) -> None:
        with pytest.raises(StockSourceNotFoundError):
            DjangoStockSourceRepository().get(StockSourceCode("ghost"))


class TestReserve:
    def test_reserve_lowers_available_and_leaves_on_hand(self) -> None:
        _level("HB-250", _source("main"), on_hand=5)
        repo = DjangoStockLevelRepository()

        repo.reserve("HB-250", 3)

        assert repo.available_for_skus(["HB-250"]) == {"HB-250": 2}
        assert repo.total_on_hand("HB-250") == 5  # physical count untouched

    def test_reserve_spills_across_sources_most_available_first(self) -> None:
        # Two sources; the planner fills from the most-available first, then the next.
        repo = DjangoStockLevelRepository()
        _level("HB-250", _source("small"), on_hand=2)
        _level("HB-250", _source("big"), on_hand=10)

        repo.reserve("HB-250", 11)

        levels = {level.source_code.value: level for level in repo.levels_for("HB-250")}
        assert levels["big"].reserved.value == 10
        assert levels["small"].reserved.value == 1
        assert repo.available_for_skus(["HB-250"]) == {"HB-250": 1}

    def test_reserve_beyond_available_raises_and_moves_nothing(self) -> None:
        _level("HB-250", _source("main"), on_hand=2)
        repo = DjangoStockLevelRepository()

        with pytest.raises(InsufficientStockError) as exc:
            repo.reserve("HB-250", 3)

        assert exc.value.available == 2
        assert repo.available_for_skus(["HB-250"]) == {"HB-250": 2}  # untouched

    def test_reserving_the_last_unit_twice_refuses_the_second(self) -> None:
        # The anti-overselling guarantee at the persistence boundary: once the single unit is
        # reserved there is nothing left to promise, so a second reservation is refused.
        _level("HB-250", _source("main"), on_hand=1)
        repo = DjangoStockLevelRepository()

        repo.reserve("HB-250", 1)
        with pytest.raises(InsufficientStockError):
            repo.reserve("HB-250", 1)

        assert repo.available_for_skus(["HB-250"]) == {"HB-250": 0}


class TestRelease:
    def test_release_restores_available(self) -> None:
        _level("HB-250", _source("main"), on_hand=5, reserved=3)
        repo = DjangoStockLevelRepository()

        repo.release("HB-250", 2)

        assert repo.available_for_skus(["HB-250"]) == {"HB-250": 4}
        assert repo.total_on_hand("HB-250") == 5

    def test_release_draws_from_the_most_reserved_source_first(self) -> None:
        repo = DjangoStockLevelRepository()
        _level("HB-250", _source("a"), on_hand=5, reserved=1)
        _level("HB-250", _source("b"), on_hand=5, reserved=4)

        repo.release("HB-250", 4)

        levels = {level.source_code.value: level for level in repo.levels_for("HB-250")}
        assert levels["b"].reserved.value == 0
        assert levels["a"].reserved.value == 1


class TestSetAndAdjustOnHand:
    def test_set_on_hand_creates_the_level_lazily(self) -> None:
        _source("main")
        repo = DjangoStockLevelRepository()

        repo.set_on_hand("NEW-1", StockSourceCode("main"), 7)

        assert repo.total_on_hand("NEW-1") == 7

    def test_set_on_hand_cannot_drop_below_reserved(self) -> None:
        _level("HB-250", _source("main"), on_hand=5, reserved=3)
        repo = DjangoStockLevelRepository()

        with pytest.raises(InsufficientStockError):
            repo.set_on_hand("HB-250", StockSourceCode("main"), 2)

        assert repo.total_on_hand("HB-250") == 5  # unchanged

    def test_adjust_on_hand_accumulates(self) -> None:
        _level("HB-250", _source("main"), on_hand=5)
        repo = DjangoStockLevelRepository()

        repo.adjust_on_hand("HB-250", StockSourceCode("main"), 4)
        repo.adjust_on_hand("HB-250", StockSourceCode("main"), -2)

        assert repo.total_on_hand("HB-250") == 7

    def test_adjust_on_hand_cannot_go_below_reserved(self) -> None:
        _level("HB-250", _source("main"), on_hand=5, reserved=4)
        repo = DjangoStockLevelRepository()

        with pytest.raises(InsufficientStockError):
            repo.adjust_on_hand("HB-250", StockSourceCode("main"), -2)

        assert repo.total_on_hand("HB-250") == 5

    def test_set_on_hand_on_an_unknown_source_raises(self) -> None:
        repo = DjangoStockLevelRepository()

        with pytest.raises(StockSourceNotFoundError):
            repo.set_on_hand("HB-250", StockSourceCode("ghost"), 3)


class TestAggregateReads:
    def test_total_on_hand_sums_across_sources(self) -> None:
        repo = DjangoStockLevelRepository()
        _level("HB-250", _source("a"), on_hand=3)
        _level("HB-250", _source("b"), on_hand=4)

        assert repo.total_on_hand("HB-250") == 7

    def test_available_for_skus_is_a_batch_of_on_hand_minus_reserved(self) -> None:
        repo = DjangoStockLevelRepository()
        main = _source("main")
        _level("HB-250", main, on_hand=5, reserved=2)
        _level("DR-250", main, on_hand=1)

        assert repo.available_for_skus(["HB-250", "DR-250", "MISSING"]) == {
            "HB-250": 3,
            "DR-250": 1,
        }

    def test_available_for_skus_returns_empty_for_no_skus(self) -> None:
        assert DjangoStockLevelRepository().available_for_skus([]) == {}

    def test_on_hand_at_returns_the_source_count_or_zero(self) -> None:
        repo = DjangoStockLevelRepository()
        _level("HB-250", _source("main"), on_hand=7)

        assert repo.on_hand_at("HB-250", StockSourceCode("main")) == 7
        assert repo.on_hand_at("HB-250", StockSourceCode("main")) == 7
        assert repo.on_hand_at("MISSING", StockSourceCode("main")) == 0


class TestModelRepr:
    def test_source_str_is_its_code(self) -> None:
        assert str(_source("warehouse-north")) == "warehouse-north"

    def test_level_str_names_the_sku_source_and_counts(self) -> None:
        source = _source("main")
        _level("HB-250", source, on_hand=5, reserved=2)

        level = StockLevelModel.objects.get(sku="HB-250", source=source)
        assert str(level) == f"HB-250@{source.pk}:5/2"

    def test_policy_str_summarises_backorder_and_threshold(self) -> None:
        _policy("HB-250", backorderable=True, low_stock_threshold=4)
        policy = StockPolicyModel.objects.get(sku="HB-250")
        assert str(policy) == "HB-250:backorder:threshold=4"

        _policy("DR-250")
        assert str(StockPolicyModel.objects.get(sku="DR-250")) == "DR-250:no-backorder:threshold=0"


class TestDatabaseConstraint:
    def test_reserved_can_never_exceed_on_hand_at_the_database(self) -> None:
        # The domain and adapter both guard this; the CheckConstraint is the last backstop
        # against a raw over-reserve slipping in (e.g. a future direct write).
        _level("HB-250", _source("main"), on_hand=2)

        with pytest.raises(IntegrityError), transaction.atomic():
            StockLevelModel.objects.filter(sku="HB-250").update(reserved=F("on_hand") + 1)


def _policy(sku: str, *, backorderable: bool = False, low_stock_threshold: int = 0) -> None:
    StockPolicyModel.objects.create(
        sku=sku, backorderable=backorderable, low_stock_threshold=low_stock_threshold
    )


class TestBackorderReserve:
    def test_backorderable_reserves_physical_then_tracks_the_overflow(self) -> None:
        # 3 on hand, backorderable; reserving 5 reserves the 3 physical and backorders 2 --
        # the per-source reserved==on_hand invariant is never violated.
        _level("HB-250", _source("main"), on_hand=3)
        _policy("HB-250", backorderable=True)
        repo = DjangoStockLevelRepository()

        repo.reserve("HB-250", 5)

        level = StockLevelModel.objects.get(sku="HB-250", source__code="main")
        assert level.reserved == 3 == level.on_hand
        assert StockPolicyModel.objects.get(sku="HB-250").backordered == 2
        # Available-to-promise reads as fully committed (0), not negative.
        assert repo.available_for_skus(["HB-250"]) == {"HB-250": 0}

    def test_non_backorderable_still_refuses_past_available(self) -> None:
        _level("HB-250", _source("main"), on_hand=1)
        repo = DjangoStockLevelRepository()

        with pytest.raises(InsufficientStockError):
            repo.reserve("HB-250", 2)

        # No policy row is needed to refuse; nothing was backordered.
        assert not StockPolicyModel.objects.filter(sku="HB-250", backordered__gt=0).exists()

    def test_release_frees_backorder_before_physical(self) -> None:
        _level("HB-250", _source("main"), on_hand=3)
        _policy("HB-250", backorderable=True)
        repo = DjangoStockLevelRepository()
        repo.reserve("HB-250", 5)  # reserved=3 physical, backordered=2

        # Releasing 3 clears the 2 backorder first, then 1 physical reservation.
        repo.release("HB-250", 3)

        level = StockLevelModel.objects.get(sku="HB-250", source__code="main")
        assert level.reserved == 2
        assert StockPolicyModel.objects.get(sku="HB-250").backordered == 0

    def test_release_without_backorder_only_touches_physical(self) -> None:
        _level("HB-250", _source("main"), on_hand=5, reserved=3)
        repo = DjangoStockLevelRepository()

        repo.release("HB-250", 2)

        level = StockLevelModel.objects.get(sku="HB-250", source__code="main")
        assert level.reserved == 1

    def test_release_only_backorder_leaves_physical_untouched(self) -> None:
        # All promised units are backorder (no physical stock): releasing them frees only
        # the backorder counter, never touching a level row.
        _policy("HB-250", backorderable=True)
        repo = DjangoStockLevelRepository()
        repo.reserve("HB-250", 3)  # no levels -> all 3 backordered
        assert StockPolicyModel.objects.get(sku="HB-250").backordered == 3

        repo.release("HB-250", 3)

        assert StockPolicyModel.objects.get(sku="HB-250").backordered == 0
        assert not StockLevelModel.objects.filter(sku="HB-250").exists()


class TestStockPolicyRepository:
    def test_get_returns_the_default_when_unset(self) -> None:
        policy = DjangoStockPolicyRepository().get("NEW-1")
        assert policy.backorderable is False
        assert policy.low_stock_threshold == 0
        assert policy.backordered.value == 0

    def test_set_policy_upserts_without_touching_backordered(self) -> None:
        repo = DjangoStockPolicyRepository()
        # Simulate an in-flight backorder, then re-configure the policy.
        StockPolicyModel.objects.create(sku="HB-250", backordered=4)

        stored = repo.set_policy("HB-250", backorderable=True, low_stock_threshold=3)

        assert stored.backorderable is True
        assert stored.low_stock_threshold == 3
        assert stored.backordered.value == 4  # movement state preserved

    def test_backorderable_skus_filters_the_flagged_subset(self) -> None:
        _policy("A-1", backorderable=True)
        _policy("B-1", backorderable=False)

        assert DjangoStockPolicyRepository().backorderable_skus(["A-1", "B-1", "C-1"]) == {"A-1"}

    def test_backorderable_skus_empty_input(self) -> None:
        assert DjangoStockPolicyRepository().backorderable_skus([]) == set()


class TestLowStockAlert:
    def test_alert_fires_when_available_drops_to_threshold(self) -> None:
        _level("HB-250", _source("main"), on_hand=10)
        _policy("HB-250", low_stock_threshold=3)
        repo = DjangoStockLevelRepository()

        with capture_logs() as logs:
            repo.reserve("HB-250", 8)  # available 10 -> 2, at/below threshold 3

        low = [e for e in logs if e["event"] == "stock_low"]
        assert low and low[0]["available"] == 2 and low[0]["threshold"] == 3

    def test_no_alert_above_threshold(self) -> None:
        _level("HB-250", _source("main"), on_hand=10)
        _policy("HB-250", low_stock_threshold=3)
        repo = DjangoStockLevelRepository()

        with capture_logs() as logs:
            repo.reserve("HB-250", 2)  # available -> 8, above threshold

        assert not [e for e in logs if e["event"] == "stock_low"]
