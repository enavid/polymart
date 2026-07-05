"""URL patterns for the payment slice.

There is no owner id in the URL space: every route resolves the payment/order from the
authenticated user (or the guest's session cookie), and the references are opaque, so one
shopper can never address another's payment.
"""

from __future__ import annotations

from django.urls import path

from src.interface.api.payment.views import (
    PaymentCollectionView,
    PaymentDetailView,
    PaymentForOrderView,
)

urlpatterns = [
    path("payments/", PaymentCollectionView.as_view(), name="payments"),
    # Declared before the ``<reference>`` detail route so "for-order" is not read as one.
    path(
        "payments/for-order/<str:number>/",
        PaymentForOrderView.as_view(),
        name="payment-for-order",
    ),
    path("payments/<str:reference>/", PaymentDetailView.as_view(), name="payment-detail"),
]
