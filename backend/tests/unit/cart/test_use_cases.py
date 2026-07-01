"""Unit tests for the cart use cases (fakes, no DB)."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from src.application.cart.ports import CartRepository, ChannelReader, VariantPricingReader
from src.application.cart.use_cases import (
    AddCartItem,
    AddCartItemCommand,
    GetCart,
    GetCartQuery,
    RemoveCartItem,
    RemoveCartItemCommand,
    UpdateCartItem,
    UpdateCartItemCommand,
)
from src.domain.cart.entities import Cart
from src.domain.cart.exceptions import (
    CartLineNotFoundError,
    InvalidCartQuantityError,
    InvalidSkuError,
    UnknownChannelError,
    VariantNotFoundError,
    VariantNotPurchasableError,
)
from src.domain.cart.value_objects import ChannelRef, Money

_CHANNEL = "ir-main"


class FakeCartRepository(CartRepository):
    def __init__(self) -> None:
        self._carts: dict[tuple[str, str], Cart] = {}

    def get(self, owner: str, channel: str) -> Cart:
        existing = self._carts.get((owner, channel))
        if existing is not None:
            return existing
        return Cart(owner=owner, channel=ChannelRef(channel))

    def apply(self, owner: str, channel: str, mutate: Callable[[Cart], None]) -> Cart:
        cart = self.get(owner, channel)
        # mutate may raise (e.g. a missing line); nothing is stored in that case,
        # mirroring the real adapter's transactional rollback.
        mutate(cart)
        cart.id = 1
        self._carts[(owner, channel)] = cart
        return cart


class FakeVariantPricingReader(VariantPricingReader):
    def __init__(self) -> None:
        self._exists: set[str] = set()
        self._prices: dict[tuple[str, str], Money] = {}

    def seed(self, sku: str, *, channel: str, amount: str | None) -> None:
        self._exists.add(sku)
        if amount is not None:
            self._prices[(sku, channel)] = Money(amount=Decimal(amount), currency="IRR")

    def unprice(self, sku: str, *, channel: str) -> None:
        self._prices.pop((sku, channel), None)

    def exists(self, sku: str) -> bool:
        return sku in self._exists

    def price_of(self, sku: str, channel: str) -> Money | None:
        return self._prices.get((sku, channel))


class FakeChannelReader(ChannelReader):
    def __init__(self) -> None:
        self._currencies = {_CHANNEL: "IRR"}

    def currency_of(self, channel: str) -> str | None:
        return self._currencies.get(channel)


@pytest.fixture
def carts() -> FakeCartRepository:
    return FakeCartRepository()


@pytest.fixture
def pricing() -> FakeVariantPricingReader:
    reader = FakeVariantPricingReader()
    reader.seed("HB-250", channel=_CHANNEL, amount="120000.00")
    reader.seed("HB-500", channel=_CHANNEL, amount="200000.00")
    return reader


@pytest.fixture
def channels() -> FakeChannelReader:
    return FakeChannelReader()


class TestAddCartItem:
    def test_adds_a_line_and_prices_it(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        use_case = AddCartItem(carts, pricing, channels)

        priced = use_case.execute(
            AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=2)
        )

        assert priced.currency == "IRR"
        assert priced.lines[0].line_total == Money(amount=Decimal("240000.00"), currency="IRR")
        assert priced.total == Money(amount=Decimal("240000.00"), currency="IRR")

    def test_incrementing_the_same_sku_accumulates(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        use_case = AddCartItem(carts, pricing, channels)
        use_case.execute(AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=2))

        priced = use_case.execute(
            AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=3)
        )

        assert len(priced.lines) == 1
        assert priced.lines[0].quantity.value == 5

    def test_persists_across_reads(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        AddCartItem(carts, pricing, channels).execute(
            AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=2)
        )

        priced = GetCart(carts, pricing, channels).execute(
            GetCartQuery(owner="7", channel=_CHANNEL)
        )

        assert priced.lines[0].sku.value == "HB-250"

    def test_unknown_variant_raises_not_found(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        with pytest.raises(VariantNotFoundError):
            AddCartItem(carts, pricing, channels).execute(
                AddCartItemCommand(owner="7", channel=_CHANNEL, sku="GHOST", quantity=1)
            )

    def test_variant_without_a_price_in_the_channel_is_not_purchasable(
        self, carts: FakeCartRepository, channels: FakeChannelReader
    ) -> None:
        pricing = FakeVariantPricingReader()
        pricing.seed("HB-250", channel=_CHANNEL, amount=None)  # exists but no price

        with pytest.raises(VariantNotPurchasableError):
            AddCartItem(carts, pricing, channels).execute(
                AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=1)
            )

    def test_unknown_channel_raises(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        with pytest.raises(UnknownChannelError):
            AddCartItem(carts, pricing, channels).execute(
                AddCartItemCommand(owner="7", channel="nope", sku="HB-250", quantity=1)
            )

    def test_malformed_sku_and_quantity_fail_fast(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        use_case = AddCartItem(carts, pricing, channels)
        with pytest.raises(InvalidSkuError):
            use_case.execute(
                AddCartItemCommand(owner="7", channel=_CHANNEL, sku="bad sku", quantity=1)
            )
        with pytest.raises(InvalidCartQuantityError):
            use_case.execute(
                AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=0)
            )

    def test_logs_without_price_or_pii(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        with capture_logs() as logs:
            AddCartItem(carts, pricing, channels).execute(
                AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=2)
            )

        event = next(e for e in logs if e["event"] == "cart_item_added")
        assert event["owner"] == "7"
        assert event["sku"] == "HB-250"
        # A money-sensitive value must never appear in the structured logs.
        assert not any("amount" in key or "price" in key or "total" in key for key in event)

    def test_two_owners_have_isolated_carts(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        add = AddCartItem(carts, pricing, channels)
        add.execute(AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=1))
        add.execute(AddCartItemCommand(owner="8", channel=_CHANNEL, sku="HB-500", quantity=1))

        cart7 = GetCart(carts, pricing, channels).execute(GetCartQuery(owner="7", channel=_CHANNEL))
        assert [line.sku.value for line in cart7.lines] == ["HB-250"]


class TestGetCart:
    def test_empty_cart_totals_zero(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        priced = GetCart(carts, pricing, channels).execute(
            GetCartQuery(owner="7", channel=_CHANNEL)
        )

        assert priced.lines == ()
        assert priced.total == Money.zero("IRR")

    def test_unknown_channel_raises(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        with pytest.raises(UnknownChannelError):
            GetCart(carts, pricing, channels).execute(GetCartQuery(owner="7", channel="nope"))

    def test_a_line_that_loses_its_price_becomes_unavailable(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        AddCartItem(carts, pricing, channels).execute(
            AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=2)
        )
        # The channel price is withdrawn after the item is already in the cart.
        pricing.unprice("HB-250", channel=_CHANNEL)

        priced = GetCart(carts, pricing, channels).execute(
            GetCartQuery(owner="7", channel=_CHANNEL)
        )

        assert priced.lines[0].available is False
        assert priced.total == Money.zero("IRR")


class TestUpdateCartItem:
    def test_sets_the_quantity(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        AddCartItem(carts, pricing, channels).execute(
            AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=2)
        )

        priced = UpdateCartItem(carts, pricing, channels).execute(
            UpdateCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=9)
        )

        assert priced.lines[0].quantity.value == 9

    def test_unknown_line_raises_not_found(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        with pytest.raises(CartLineNotFoundError):
            UpdateCartItem(carts, pricing, channels).execute(
                UpdateCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=3)
            )


class TestRemoveCartItem:
    def test_removes_the_line(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        AddCartItem(carts, pricing, channels).execute(
            AddCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250", quantity=2)
        )

        priced = RemoveCartItem(carts, pricing, channels).execute(
            RemoveCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250")
        )

        assert priced.lines == ()

    def test_unknown_line_raises_not_found(
        self,
        carts: FakeCartRepository,
        pricing: FakeVariantPricingReader,
        channels: FakeChannelReader,
    ) -> None:
        with pytest.raises(CartLineNotFoundError):
            RemoveCartItem(carts, pricing, channels).execute(
                RemoveCartItemCommand(owner="7", channel=_CHANNEL, sku="HB-250")
            )
