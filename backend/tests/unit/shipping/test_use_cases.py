"""Unit tests for the shipping use cases against a fake reader (no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.shipping.ports import ShippingMethodReader
from src.application.shipping.use_cases import (
    GetShippingMethod,
    ListShippingMethods,
    ListShippingMethodsQuery,
)
from src.domain.shipping.entities import ShippingMethod
from src.domain.shipping.exceptions import ShippingMethodNotFoundError
from src.domain.shipping.value_objects import Money, ShippingMethodCode


def _method(code: str, amount: str) -> ShippingMethod:
    return ShippingMethod(
        code=ShippingMethodCode(code),
        name=code.title(),
        price=Money(Decimal(amount), "IRR"),
        min_days=2,
        max_days=4,
    )


class FakeReader(ShippingMethodReader):
    def __init__(self, methods: dict[str, tuple[ShippingMethod, ...]]) -> None:
        self._methods = methods

    def available_for(self, channel: str) -> tuple[ShippingMethod, ...]:
        return self._methods.get(channel, ())

    def get(self, channel: str, code: str) -> ShippingMethod | None:
        for method in self._methods.get(channel, ()):
            if method.code.value == code:
                return method
        return None


_METHODS = {
    "ir-main": (_method("standard", "50000"), _method("express", "120000")),
}


class TestListShippingMethods:
    def test_lists_the_channels_methods(self) -> None:
        result = ListShippingMethods(FakeReader(_METHODS)).execute(
            ListShippingMethodsQuery(channel="ir-main")
        )
        assert [m.code.value for m in result] == ["standard", "express"]

    def test_an_unconfigured_channel_lists_nothing(self) -> None:
        result = ListShippingMethods(FakeReader(_METHODS)).execute(
            ListShippingMethodsQuery(channel="ghost")
        )
        assert result == ()


class TestGetShippingMethod:
    def test_resolves_a_known_method(self) -> None:
        method = GetShippingMethod(FakeReader(_METHODS)).execute(channel="ir-main", code="express")
        assert method.price.amount == Decimal("120000")

    def test_an_unknown_method_raises(self) -> None:
        with pytest.raises(ShippingMethodNotFoundError):
            GetShippingMethod(FakeReader(_METHODS)).execute(channel="ir-main", code="drone")

    def test_a_method_in_another_channel_is_not_found(self) -> None:
        with pytest.raises(ShippingMethodNotFoundError):
            GetShippingMethod(FakeReader(_METHODS)).execute(channel="ghost", code="standard")
