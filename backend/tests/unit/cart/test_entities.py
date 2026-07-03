"""Unit tests for the Cart aggregate (pure domain, no framework)."""

from __future__ import annotations

import pytest

from src.domain.cart.entities import Cart, CartLine
from src.domain.cart.exceptions import CartLineNotFoundError, DuplicateCartLineError
from src.domain.cart.value_objects import CartQuantity, ChannelRef, Sku


def _cart() -> Cart:
    return Cart(owner="7", channel=ChannelRef("ir-main"))


class TestAddItem:
    def test_appends_a_new_line(self) -> None:
        cart = _cart()

        cart.add_item(Sku("HB-250"), CartQuantity(2))

        assert cart.lines == [CartLine(sku=Sku("HB-250"), quantity=CartQuantity(2))]

    def test_increments_an_existing_line(self) -> None:
        cart = _cart()
        cart.add_item(Sku("HB-250"), CartQuantity(2))

        cart.add_item(Sku("HB-250"), CartQuantity(3))

        assert len(cart.lines) == 1
        assert cart.lines[0].quantity == CartQuantity(5)

    def test_keeps_distinct_skus_separate_and_ordered(self) -> None:
        cart = _cart()

        cart.add_item(Sku("HB-250"), CartQuantity(1))
        cart.add_item(Sku("HB-500"), CartQuantity(1))

        assert [line.sku.value for line in cart.lines] == ["HB-250", "HB-500"]

    def test_incrementing_past_the_maximum_is_rejected(self) -> None:
        cart = _cart()
        cart.add_item(Sku("HB-250"), CartQuantity(1_000_000))

        with pytest.raises(Exception):  # noqa: B017 - InvalidCartQuantityError from the VO
            cart.add_item(Sku("HB-250"), CartQuantity(1))


class TestSetItem:
    def test_replaces_the_quantity(self) -> None:
        cart = _cart()
        cart.add_item(Sku("HB-250"), CartQuantity(2))

        cart.set_item(Sku("HB-250"), CartQuantity(9))

        assert cart.lines[0].quantity == CartQuantity(9)

    def test_unknown_line_raises(self) -> None:
        cart = _cart()

        with pytest.raises(CartLineNotFoundError):
            cart.set_item(Sku("GHOST"), CartQuantity(1))


class TestRemoveItem:
    def test_removes_the_line(self) -> None:
        cart = _cart()
        cart.add_item(Sku("HB-250"), CartQuantity(2))
        cart.add_item(Sku("HB-500"), CartQuantity(1))

        cart.remove_item(Sku("HB-250"))

        assert [line.sku.value for line in cart.lines] == ["HB-500"]

    def test_unknown_line_raises(self) -> None:
        cart = _cart()

        with pytest.raises(CartLineNotFoundError):
            cart.remove_item(Sku("GHOST"))


class TestMergeFrom:
    def _other(self) -> Cart:
        return Cart(owner="g:tok", channel=ChannelRef("ir-main"))

    def test_appends_lines_the_target_does_not_have(self) -> None:
        cart = _cart()
        cart.add_item(Sku("HB-250"), CartQuantity(1))
        other = self._other()
        other.add_item(Sku("HB-500"), CartQuantity(2))

        cart.merge_from(other)

        assert [(line.sku.value, line.quantity.value) for line in cart.lines] == [
            ("HB-250", 1),
            ("HB-500", 2),
        ]

    def test_sums_quantities_for_a_shared_sku(self) -> None:
        cart = _cart()
        cart.add_item(Sku("HB-250"), CartQuantity(2))
        other = self._other()
        other.add_item(Sku("HB-250"), CartQuantity(3))

        cart.merge_from(other)

        assert len(cart.lines) == 1
        assert cart.lines[0].quantity == CartQuantity(5)

    def test_caps_a_summed_quantity_instead_of_raising(self) -> None:
        cart = _cart()
        cart.add_item(Sku("HB-250"), CartQuantity(1_000_000))
        other = self._other()
        other.add_item(Sku("HB-250"), CartQuantity(500))

        cart.merge_from(other)

        assert cart.lines[0].quantity == CartQuantity(1_000_000)

    def test_merging_an_empty_cart_is_a_no_op(self) -> None:
        cart = _cart()
        cart.add_item(Sku("HB-250"), CartQuantity(1))

        cart.merge_from(self._other())

        assert [line.sku.value for line in cart.lines] == ["HB-250"]

    def test_preserves_target_order_then_appends_new_skus(self) -> None:
        cart = _cart()
        cart.add_item(Sku("HB-250"), CartQuantity(1))
        cart.add_item(Sku("HB-500"), CartQuantity(1))
        other = self._other()
        other.add_item(Sku("HB-500"), CartQuantity(1))
        other.add_item(Sku("HB-1000"), CartQuantity(1))

        cart.merge_from(other)

        assert [line.sku.value for line in cart.lines] == ["HB-250", "HB-500", "HB-1000"]


class TestInvariant:
    def test_rebuilding_with_a_duplicate_sku_is_rejected(self) -> None:
        with pytest.raises(DuplicateCartLineError):
            Cart(
                owner="7",
                channel=ChannelRef("ir-main"),
                lines=[
                    CartLine(sku=Sku("HB-250"), quantity=CartQuantity(1)),
                    CartLine(sku=Sku("HB-250"), quantity=CartQuantity(2)),
                ],
            )
