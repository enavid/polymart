"""Unit tests for the ShippingMethod entity (pure Python, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.shipping.entities import ShippingMethod
from src.domain.shipping.exceptions import InvalidShippingMethodError
from src.domain.shipping.value_objects import Money, ShippingMethodCode


def _method(**overrides: object) -> ShippingMethod:
    kwargs: dict[str, object] = {
        "code": ShippingMethodCode("standard"),
        "name": "Standard post",
        "price": Money(Decimal("50000"), "IRR"),
        "min_days": 3,
        "max_days": 5,
    }
    kwargs.update(overrides)
    return ShippingMethod(**kwargs)  # type: ignore[arg-type]


class TestShippingMethod:
    def test_builds_a_valid_method(self) -> None:
        method = _method()
        assert method.code.value == "standard"
        assert method.name == "Standard post"
        assert method.price.amount == Decimal("50000")
        assert (method.min_days, method.max_days) == (3, 5)

    def test_trims_the_name(self) -> None:
        assert _method(name="  Express  ").name == "Express"

    def test_a_same_day_window_is_valid(self) -> None:
        method = _method(min_days=0, max_days=0)
        assert (method.min_days, method.max_days) == (0, 0)

    def test_rejects_a_blank_name(self) -> None:
        with pytest.raises(InvalidShippingMethodError):
            _method(name="   ")

    def test_rejects_a_window_that_ends_before_it_starts(self) -> None:
        with pytest.raises(InvalidShippingMethodError):
            _method(min_days=5, max_days=3)

    def test_rejects_a_negative_day(self) -> None:
        with pytest.raises(InvalidShippingMethodError):
            _method(min_days=-1)

    def test_rejects_a_boolean_day_count(self) -> None:
        with pytest.raises(InvalidShippingMethodError):
            _method(min_days=True)
