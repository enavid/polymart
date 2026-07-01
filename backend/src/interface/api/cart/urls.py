"""URL patterns for the cart slice.

There is no cart id in the URL space: every route resolves the cart from the
authenticated user, so one shopper can never address another's cart.
"""

from __future__ import annotations

from django.urls import path

from src.interface.api.cart.views import CartItemDetailView, CartItemsView, CartView

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/items/", CartItemsView.as_view(), name="cart-items"),
    path("cart/items/<str:sku>/", CartItemDetailView.as_view(), name="cart-item-detail"),
]
