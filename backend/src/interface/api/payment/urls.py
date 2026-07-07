"""URL patterns for the payment slice.

There is no owner id in the URL space: every route resolves the payment/order from the
authenticated user (or the guest's session cookie), and the references are opaque, so one
shopper can never address another's payment.
"""

from __future__ import annotations

from django.urls import path

from src.interface.api.payment.views import (
    CardToCardConfirmView,
    CardToCardInstructionsView,
    CardToCardRejectView,
    MockGatewayView,
    PaymentCallbackView,
    PaymentCollectionView,
    PaymentDetailView,
    PaymentForOrderView,
    PaymentRefundView,
    TransferReferenceView,
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
    # Card-to-card (owner-scoped): read the destination card and submit the transfer reference.
    path(
        "payments/for-order/<str:number>/card-to-card/",
        CardToCardInstructionsView.as_view(),
        name="payment-card-to-card-instructions",
    ),
    path(
        "payments/for-order/<str:number>/transfer-reference/",
        TransferReferenceView.as_view(),
        name="payment-transfer-reference",
    ),
    path("payments/callback/", PaymentCallbackView.as_view(), name="payment-callback"),
    path("payments/mock-gateway/", MockGatewayView.as_view(), name="payment-mock-gateway"),
    # The reference sub-paths (an extra segment) are declared before the ``<reference>`` detail
    # route for clarity, though the extra segment already keeps them distinct.
    path(
        "payments/<str:reference>/refund/",
        PaymentRefundView.as_view(),
        name="payment-refund",
    ),
    # Card-to-card staff settlement (manage_orders): confirm captures, reject fails.
    path(
        "payments/<str:reference>/confirm/",
        CardToCardConfirmView.as_view(),
        name="payment-card-to-card-confirm",
    ),
    path(
        "payments/<str:reference>/reject/",
        CardToCardRejectView.as_view(),
        name="payment-card-to-card-reject",
    ),
    path("payments/<str:reference>/", PaymentDetailView.as_view(), name="payment-detail"),
]
