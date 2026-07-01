"""Composition root for the cart slice.

The only place that wires concrete infrastructure adapters into the use cases.
Views depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.cart.use_cases import (
    AddCartItem,
    GetCart,
    RemoveCartItem,
    UpdateCartItem,
)
from src.infrastructure.cart.repositories import (
    DjangoCartRepository,
    DjangoChannelReader,
    DjangoVariantPricingReader,
)


def build_get_cart() -> GetCart:
    return GetCart(
        DjangoCartRepository(), DjangoVariantPricingReader(), DjangoChannelReader()
    )


def build_add_cart_item() -> AddCartItem:
    return AddCartItem(
        DjangoCartRepository(), DjangoVariantPricingReader(), DjangoChannelReader()
    )


def build_update_cart_item() -> UpdateCartItem:
    return UpdateCartItem(
        DjangoCartRepository(), DjangoVariantPricingReader(), DjangoChannelReader()
    )


def build_remove_cart_item() -> RemoveCartItem:
    return RemoveCartItem(
        DjangoCartRepository(), DjangoVariantPricingReader(), DjangoChannelReader()
    )
