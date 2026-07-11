"""Unit tests for the order value objects (pure, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.order.exceptions import (
    InvalidCapturedShippingError,
    InvalidChannelReferenceError,
    InvalidMoneyError,
    InvalidOrderNumberError,
    InvalidOrderQuantityError,
    InvalidShippingAddressError,
    InvalidSkuError,
)
from src.domain.order.value_objects import (
    CapturedShipping,
    ChannelRef,
    Money,
    OrderNumber,
    OrderQuantity,
    OrderStatus,
    ShippingAddress,
    Sku,
)


class TestSku:
    def test_canonicalises_to_upper_case(self) -> None:
        assert Sku("hb-250").value == "HB-250"

    def test_strips_surrounding_whitespace(self) -> None:
        assert Sku("  hb-250 ").value == "HB-250"

    @pytest.mark.parametrize("bad", ["", "hb 250", "hb_250", "-hb", "hb-", "x" * 65])
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(InvalidSkuError):
            Sku(bad)


class TestOrderQuantity:
    def test_accepts_a_positive_integer(self) -> None:
        assert OrderQuantity(3).value == 3

    @pytest.mark.parametrize("bad", [0, -1, 1_000_001])
    def test_rejects_out_of_range(self, bad: int) -> None:
        with pytest.raises(InvalidOrderQuantityError):
            OrderQuantity(bad)

    def test_rejects_bool(self) -> None:
        # bool is an int subclass; True must never become a quantity of one.
        with pytest.raises(InvalidOrderQuantityError):
            OrderQuantity(True)

    def test_rejects_non_integer(self) -> None:
        with pytest.raises(InvalidOrderQuantityError):
            OrderQuantity(2.5)  # type: ignore[arg-type]


class TestChannelRef:
    def test_keeps_a_valid_slug(self) -> None:
        assert ChannelRef("ir-main").value == "ir-main"

    @pytest.mark.parametrize("bad", ["", "   ", "x" * 65])
    def test_rejects_blank_or_too_long(self, bad: str) -> None:
        with pytest.raises(InvalidChannelReferenceError):
            ChannelRef(bad)


class TestOrderNumber:
    def test_canonicalises_to_upper_case(self) -> None:
        assert OrderNumber("ord-abc123").value == "ORD-ABC123"

    @pytest.mark.parametrize("bad", ["", "short", "ord abc", "x" * 41, "ord_1"])
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(InvalidOrderNumberError):
            OrderNumber(bad)


class TestMoney:
    def test_requires_a_decimal_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=1200.0, currency="IRR")  # type: ignore[arg-type]

    def test_rejects_a_negative_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("-1"), currency="IRR")

    def test_rejects_a_non_finite_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("NaN"), currency="IRR")

    def test_rejects_too_many_decimal_places(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1.00001"), currency="IRR")

    def test_rejects_too_many_digits(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1" * 19), currency="IRR")

    @pytest.mark.parametrize("bad", ["ir", "IRRR", "12", ""])
    def test_rejects_a_malformed_currency(self, bad: str) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1"), currency=bad)

    def test_normalises_currency_case(self) -> None:
        assert Money(amount=Decimal("1"), currency="irr").currency == "IRR"

    def test_zero_is_a_zero_amount(self) -> None:
        assert Money.zero("IRR").amount == Decimal("0")

    def test_times_scales_exactly(self) -> None:
        product = Money(amount=Decimal("120000.00"), currency="IRR").times(OrderQuantity(3))
        assert product.amount == Decimal("360000.00")

    def test_add_sums_same_currency(self) -> None:
        result = Money(amount=Decimal("100"), currency="IRR").add(
            Money(amount=Decimal("50"), currency="IRR")
        )
        assert result.amount == Decimal("150")

    def test_add_refuses_currency_mismatch(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1"), currency="IRR").add(
                Money(amount=Decimal("1"), currency="USD")
            )


class TestOrderStatus:
    def test_serialises_to_its_string_value(self) -> None:
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus("cancelled") is OrderStatus.CANCELLED


def _shipping_address(**overrides: str | None) -> ShippingAddress:
    fields = {
        "recipient_name": "Sara Ahmadi",
        "phone_number": "+989123456789",
        "province": "Tehran",
        "city": "Tehran",
        "postal_code": "1234567890",
        "line1": "Valiasr St, No. 1",
        "line2": None,
        **overrides,
    }
    return ShippingAddress(**fields)  # type: ignore[arg-type]


class TestShippingAddress:
    def test_builds_with_no_line2(self) -> None:
        address = _shipping_address()
        assert address.line2 is None

    def test_builds_with_a_line2(self) -> None:
        address = _shipping_address(line2="Unit 4")
        assert address.line2 == "Unit 4"

    def test_strips_surrounding_whitespace(self) -> None:
        address = _shipping_address(recipient_name="  Sara Ahmadi  ")
        assert address.recipient_name == "Sara Ahmadi"

    @pytest.mark.parametrize(
        "field",
        ["recipient_name", "phone_number", "province", "city", "postal_code", "line1"],
    )
    def test_rejects_a_blank_required_field(self, field: str) -> None:
        with pytest.raises(InvalidShippingAddressError):
            _shipping_address(**{field: "   "})

    def test_rejects_a_blank_line2_distinctly_from_omitted(self) -> None:
        # An explicit blank line2 is a malformed request, not "no line2".
        with pytest.raises(InvalidShippingAddressError):
            _shipping_address(line2="   ")

    @pytest.mark.parametrize(
        ("field", "limit"),
        [
            ("recipient_name", 200),
            ("phone_number", 20),
            ("province", 100),
            ("city", 100),
            ("postal_code", 10),
            ("line1", 255),
            ("line2", 255),
        ],
    )
    def test_rejects_a_field_beyond_its_bound(self, field: str, limit: int) -> None:
        with pytest.raises(InvalidShippingAddressError):
            _shipping_address(**{field: "x" * (limit + 1)})


class TestCapturedShipping:
    def _captured(self, **overrides: object) -> CapturedShipping:
        kwargs: dict[str, object] = {
            "method_code": "standard",
            "method_name": "Standard post",
            "cost": Money(amount=Decimal("50000.00"), currency="IRR"),
        }
        kwargs.update(overrides)
        return CapturedShipping(**kwargs)  # type: ignore[arg-type]

    def test_builds_a_valid_capture(self) -> None:
        captured = self._captured()
        assert captured.method_code == "standard"
        assert captured.method_name == "Standard post"
        assert captured.cost.amount == Decimal("50000.00")

    def test_a_zero_cost_capture_is_valid(self) -> None:
        assert self._captured(cost=Money(amount=Decimal("0"), currency="IRR")).cost.amount == 0

    def test_trims_the_code_and_name(self) -> None:
        captured = self._captured(method_code="  standard  ", method_name="  Standard  ")
        assert captured.method_code == "standard"
        assert captured.method_name == "Standard"

    def test_rejects_a_blank_code(self) -> None:
        with pytest.raises(InvalidCapturedShippingError):
            self._captured(method_code="   ")

    def test_rejects_a_blank_name(self) -> None:
        with pytest.raises(InvalidCapturedShippingError):
            self._captured(method_name="")

    def test_rejects_an_over_long_code(self) -> None:
        with pytest.raises(InvalidCapturedShippingError):
            self._captured(method_code="x" * 33)
