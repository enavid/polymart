"""Unit tests for the variant pricing use cases (fakes, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import ChannelReader, VariantPriceRepository, VariantRepository
from src.application.catalog.use_cases import (
    ChannelPriceInput,
    GetVariantPrices,
    SetVariantPrices,
    SetVariantPricesCommand,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import ProductVariant
from src.domain.catalog.exceptions import (
    DuplicateChannelPriceError,
    InvalidMoneyError,
    UnknownChannelError,
    VariantNotFoundError,
)
from src.domain.catalog.value_objects import ChannelPrice, ProductCode, Sku


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


class FakeChannelReader(ChannelReader):
    def __init__(self) -> None:
        self._currencies: dict[str, str] = {}

    def seed(self, channel: str, currency: str) -> None:
        self._currencies[channel] = currency

    def currency_of(self, channel_slug: str) -> str | None:
        return self._currencies.get(channel_slug)


class FakeVariantPriceRepository(VariantPriceRepository):
    def __init__(self) -> None:
        self._by_sku: dict[str, tuple[ChannelPrice, ...]] = {}

    def replace(
        self, sku: str, prices: Sequence[ChannelPrice]
    ) -> tuple[ChannelPrice, ...]:
        stored = tuple(sorted(prices, key=lambda price: price.channel))
        self._by_sku[sku] = stored
        return stored

    def list_for_variant(self, sku: str) -> tuple[ChannelPrice, ...]:
        return self._by_sku.get(sku, ())


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


def _input(channel: str, amount: str) -> ChannelPriceInput:
    return ChannelPriceInput(channel=channel, amount=Decimal(amount))


@pytest.fixture
def variants() -> FakeVariantRepository:
    repo = FakeVariantRepository()
    repo.seed(_variant())
    return repo


@pytest.fixture
def channels() -> FakeChannelReader:
    reader = FakeChannelReader()
    reader.seed("ir-toman", "IRR")
    reader.seed("us-store", "USD")
    return reader


@pytest.fixture
def prices() -> FakeVariantPriceRepository:
    return FakeVariantPriceRepository()


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


def _set_use_case(
    prices: FakeVariantPriceRepository,
    variants: FakeVariantRepository,
    channels: FakeChannelReader,
    audit: RecordingAudit,
) -> SetVariantPrices:
    return SetVariantPrices(prices, variants, channels, audit)


class TestSetVariantPrices:
    def test_sets_a_price_deriving_the_currency_from_the_channel(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)

        result = use_case.execute(
            SetVariantPricesCommand(variant="HB-250", prices=(_input("ir-toman", "1500"),))
        )

        assert [(p.channel, str(p.money.amount), p.money.currency) for p in result] == [
            ("ir-toman", "1500", "IRR")
        ]

    def test_prices_two_channels_in_their_own_currencies(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)

        result = use_case.execute(
            SetVariantPricesCommand(
                variant="HB-250",
                prices=(_input("us-store", "9.99"), _input("ir-toman", "1500")),
            )
        )

        assert {(p.channel, p.money.currency) for p in result} == {
            ("us-store", "USD"),
            ("ir-toman", "IRR"),
        }

    def test_replacing_with_an_empty_set_clears_all_prices(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)
        use_case.execute(
            SetVariantPricesCommand(variant="HB-250", prices=(_input("ir-toman", "1500"),))
        )

        result = use_case.execute(SetVariantPricesCommand(variant="HB-250", prices=()))

        assert result == ()

    def test_records_a_money_sensitive_audit_event_with_before_and_after(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)
        use_case.execute(
            SetVariantPricesCommand(variant="HB-250", prices=(_input("ir-toman", "1000"),))
        )

        use_case.execute(
            SetVariantPricesCommand(variant="HB-250", prices=(_input("ir-toman", "1500"),)),
            actor="42",
        )

        record = audit.records[-1]
        assert record["action"] == "variant.price_changed"
        assert record["resource_type"] == "variant"
        assert record["actor"] == "42"
        change = record["changes"][0]
        assert change.before == "ir-toman=1000 IRR"
        assert change.after == "ir-toman=1500 IRR"

    def test_logs_a_structured_event_without_the_amount(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)

        with capture_logs() as logs:
            use_case.execute(
                SetVariantPricesCommand(variant="HB-250", prices=(_input("ir-toman", "1500"),)),
                actor="42",
            )

        events = [e for e in logs if e["event"] == "variant_prices_set"]
        assert events and events[0]["actor"] == "42" and events[0]["count"] == 1
        # The amount is money-sensitive: it belongs in the audit trail, not the logs.
        assert "1500" not in str(events[0])

    def test_unknown_variant_raises_not_found(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)

        with pytest.raises(VariantNotFoundError):
            use_case.execute(
                SetVariantPricesCommand(variant="GHOST", prices=(_input("ir-toman", "1500"),))
            )

    def test_unknown_channel_raises_unknown_channel(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)

        with pytest.raises(UnknownChannelError):
            use_case.execute(
                SetVariantPricesCommand(variant="HB-250", prices=(_input("ghost", "1500"),))
            )

    def test_does_not_persist_or_audit_when_a_channel_is_unknown(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)

        with pytest.raises(UnknownChannelError):
            use_case.execute(
                SetVariantPricesCommand(variant="HB-250", prices=(_input("ghost", "1500"),))
            )

        assert prices.list_for_variant("HB-250") == ()
        assert audit.records == []

    def test_rejects_a_negative_amount(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)

        with pytest.raises(InvalidMoneyError):
            use_case.execute(
                SetVariantPricesCommand(variant="HB-250", prices=(_input("ir-toman", "-1"),))
            )

    def test_rejects_a_zero_amount(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)

        with pytest.raises(InvalidMoneyError):
            use_case.execute(
                SetVariantPricesCommand(variant="HB-250", prices=(_input("ir-toman", "0"),))
            )

    def test_rejects_two_prices_for_the_same_channel(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(prices, variants, channels, audit)

        with pytest.raises(DuplicateChannelPriceError):
            use_case.execute(
                SetVariantPricesCommand(
                    variant="HB-250",
                    prices=(_input("ir-toman", "1500"), _input("ir-toman", "1600")),
                )
            )


class TestGetVariantPrices:
    def test_returns_the_prices(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
        channels: FakeChannelReader,
        audit: RecordingAudit,
    ) -> None:
        _set_use_case(prices, variants, channels, audit).execute(
            SetVariantPricesCommand(variant="HB-250", prices=(_input("ir-toman", "1500"),))
        )

        result = GetVariantPrices(prices, variants).execute(sku="HB-250")

        assert [(p.channel, p.money.currency) for p in result] == [("ir-toman", "IRR")]

    def test_empty_for_a_variant_without_prices(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
    ) -> None:
        assert GetVariantPrices(prices, variants).execute(sku="HB-250") == ()

    def test_unknown_variant_raises_not_found(
        self,
        prices: FakeVariantPriceRepository,
        variants: FakeVariantRepository,
    ) -> None:
        with pytest.raises(VariantNotFoundError):
            GetVariantPrices(prices, variants).execute(sku="GHOST")
