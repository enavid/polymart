"""URL patterns for the tax slice."""

from __future__ import annotations

from django.urls import path

from src.interface.api.tax.views import TaxRateView

urlpatterns = [
    path("tax/rate/", TaxRateView.as_view(), name="tax-rate"),
]
