"""URL patterns for the shipping slice."""

from __future__ import annotations

from django.urls import path

from src.interface.api.shipping.views import ShippingMethodCollectionView

urlpatterns = [
    path("shipping/methods/", ShippingMethodCollectionView.as_view(), name="shipping-methods"),
]
