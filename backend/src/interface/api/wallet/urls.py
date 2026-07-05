"""URL patterns for the wallet slice.

There is no owner id in the URL space: the route resolves the wallet from the
authenticated user, so one user can never address another's wallet.
"""

from __future__ import annotations

from django.urls import path

from src.interface.api.wallet.views import MyWalletView

urlpatterns = [
    path("wallet/", MyWalletView.as_view(), name="wallet"),
]
