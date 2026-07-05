"""URL patterns for the payment slice.

There is no owner id in the URL space: every route resolves the payment/order from the
authenticated user (or the guest's session cookie), and the references are opaque, so one
shopper can never address another's payment.
"""

from __future__ import annotations

from django.urls import path

from src.interface.api.payment.views import (
    MockGatewayView,
    PaymentCallbackView,
    PaymentCollectionView,
    PaymentDetailView,
    PaymentForOrderView,
    PaymentRefundView,
)

urlpatterns = [
    path("payments/", PaymentCollectionView.as_view(), name="payments"),
    # The fixed sub-paths are declared before the ``<reference>`` detail route so they are
    # never read as a reference.
    path(
        "payments/for-order/<str:number>/",
        PaymentForOrderView.as_view(),
        name="payment-for-order",
    ),
    path("payments/callback/", PaymentCallbackView.as_view(), name="payment-callback"),
    path("payments/mock-gateway/", MockGatewayView.as_view(), name="payment-mock-gateway"),
    # The refund sub-path (an extra segment) is declared before the ``<reference>`` detail
    # route for clarity, though the extra segment already keeps them distinct.
    path(
        "payments/<str:reference>/refund/",
        PaymentRefundView.as_view(),
        name="payment-refund",
    ),
    path("payments/<str:reference>/", PaymentDetailView.as_view(), name="payment-detail"),
]
