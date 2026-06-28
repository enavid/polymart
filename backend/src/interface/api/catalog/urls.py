"""URL patterns for the catalog slice."""

from __future__ import annotations

from django.urls import path

from src.interface.api.catalog.views import AttributeDetailView, AttributeListCreateView

urlpatterns = [
    path("catalog/attributes/", AttributeListCreateView.as_view(), name="attribute-list"),
    path(
        "catalog/attributes/<slug:code>/",
        AttributeDetailView.as_view(),
        name="attribute-detail",
    ),
]
