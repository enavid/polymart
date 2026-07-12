"""URL patterns for the inventory admin slice."""

from __future__ import annotations

from django.urls import path

from src.interface.api.inventory.views import (
    SourceStockView,
    StockSourceListCreateView,
    VariantStockPolicyView,
)

urlpatterns = [
    path("inventory/sources/", StockSourceListCreateView.as_view(), name="inventory-sources"),
    path(
        "inventory/sources/<str:code>/stock/<str:sku>/",
        SourceStockView.as_view(),
        name="inventory-source-stock",
    ),
    path(
        "inventory/policies/<str:sku>/",
        VariantStockPolicyView.as_view(),
        name="inventory-variant-policy",
    ),
]
