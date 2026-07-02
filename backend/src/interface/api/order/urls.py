"""URL patterns for the order slice.

There is no owner id in the URL space: every route resolves the order from the
authenticated user, and the order number is opaque, so one shopper can never address
another's order.
"""

from __future__ import annotations

from django.urls import path

from src.interface.api.order.views import (
    OrderCancelView,
    OrderCollectionView,
    OrderDetailView,
)

urlpatterns = [
    path("orders/", OrderCollectionView.as_view(), name="orders"),
    path("orders/<str:number>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:number>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
]
