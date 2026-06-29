"""URL patterns for the catalog slice."""

from __future__ import annotations

from django.urls import path

from src.interface.api.catalog.views import (
    AttributeDetailView,
    AttributeListCreateView,
    CategoryDetailView,
    CategoryListCreateView,
    CollectionDetailView,
    CollectionListCreateView,
    CollectionProductsView,
    CollectionRuleMembersView,
    CollectionRuleView,
    ProductCategoriesView,
    ProductDetailView,
    ProductListCreateView,
    ProductTypeDetailView,
    ProductTypeListCreateView,
    ProductVariantListCreateView,
    VariantDetailView,
    VariantPricesView,
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
        "catalog/products/<slug:code>/categories/",
        ProductCategoriesView.as_view(),
        name="product-category-membership",
    ),
    path(
        "catalog/variants/<str:sku>/",
        VariantDetailView.as_view(),
        name="variant-detail",
    ),
    path(
        "catalog/variants/<str:sku>/prices/",
        VariantPricesView.as_view(),
        name="variant-prices",
    ),
    path("catalog/categories/", CategoryListCreateView.as_view(), name="category-list"),
    path(
        "catalog/categories/<slug:slug>/",
        CategoryDetailView.as_view(),
        name="category-detail",
    ),
    path("catalog/collections/", CollectionListCreateView.as_view(), name="collection-list"),
    path(
        "catalog/collections/<slug:slug>/",
        CollectionDetailView.as_view(),
        name="collection-detail",
    ),
    path(
        "catalog/collections/<slug:slug>/products/",
        CollectionProductsView.as_view(),
        name="collection-product-membership",
    ),
    path(
        "catalog/collections/<slug:slug>/rule/",
        CollectionRuleView.as_view(),
        name="collection-rule",
    ),
    path(
        "catalog/collections/<slug:slug>/rule/members/",
        CollectionRuleMembersView.as_view(),
        name="collection-rule-members",
    ),
]
