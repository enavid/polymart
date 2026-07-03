"""URL patterns for the order slice.

There is no owner id in the URL space: every route resolves the order from the
authenticated user, and the order number is opaque, so one shopper can never address
another's order.
"""

from __future__ import annotations

from django.urls import path

from src.interface.api.order.views import (
    ManualOrderView,
    OrderCancelView,
    OrderCollectionView,
    OrderDetailView,
    PreInvoiceView,
)

urlpatterns = [
    path("orders/", OrderCollectionView.as_view(), name="orders"),
    # Declared before the ``<number>`` detail route so "manual" is not read as a number.
    path("orders/manual/", ManualOrderView.as_view(), name="order-manual"),
    path("orders/<str:number>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:number>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
    path(
        "orders/<str:number>/pre-invoice/",
        PreInvoiceView.as_view(),
        name="order-pre-invoice",
    ),
]
