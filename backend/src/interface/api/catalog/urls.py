"""URL patterns for the catalog slice."""

from __future__ import annotations

from django.urls import path

from src.interface.api.catalog.views import (
    AttributeDetailView,
    AttributeListCreateView,
    ProductDetailView,
    ProductListCreateView,
    ProductTypeDetailView,
    ProductTypeListCreateView,
    ProductVariantListCreateView,
    VariantDetailView,
)

urlpatterns = [
    path("catalog/attributes/", AttributeListCreateView.as_view(), name="attribute-list"),
    path(
        "catalog/attributes/<slug:code>/",
        AttributeDetailView.as_view(),
        name="attribute-detail",
    ),
    path(
        "catalog/product-types/",
        ProductTypeListCreateView.as_view(),
        name="product-type-list",
    ),
    path(
        "catalog/product-types/<slug:code>/",
        ProductTypeDetailView.as_view(),
        name="product-type-detail",
    ),
    path("catalog/products/", ProductListCreateView.as_view(), name="product-list"),
    path(
        "catalog/products/<slug:code>/",
        ProductDetailView.as_view(),
        name="product-detail",
    ),
    path(
        "catalog/products/<slug:code>/variants/",
        ProductVariantListCreateView.as_view(),
        name="product-variant-list",
    ),
    path(
        "catalog/variants/<str:sku>/",
        VariantDetailView.as_view(),
        name="variant-detail",
    ),
]
