"""URL patterns for the address-book slice.

There is no owner id in the URL space: every route resolves addresses from the
authenticated user, and the address id is opaque, so one shopper can never address
another's saved address.
"""

from __future__ import annotations

from django.urls import path

from src.interface.api.address.views import (
    AddressCollectionView,
    AddressDetailView,
    AddressSetDefaultView,
)

urlpatterns = [
    path("addresses/", AddressCollectionView.as_view(), name="addresses"),
    path("addresses/<str:address_id>/", AddressDetailView.as_view(), name="address-detail"),
    path(
        "addresses/<str:address_id>/default/",
        AddressSetDefaultView.as_view(),
        name="address-set-default",
    ),
]
