"""Root URL configuration."""

from __future__ import annotations

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

api_v1_patterns = [
    path("", include("src.interface.api.health.urls")),
    path("", include("src.interface.api.identity.urls")),
    path("", include("src.interface.api.channel.urls")),
    path("", include("src.interface.api.access.urls")),
    path("", include("src.interface.api.audit.urls")),
    path("", include("src.interface.api.catalog.urls")),
    path("", include("src.interface.api.cart.urls")),
    path("", include("src.interface.api.order.urls")),
    path("", include("src.interface.api.address.urls")),
    path("", include("src.interface.api.payment.urls")),
    path("", include("src.interface.api.wallet.urls")),
    path("", include("src.interface.api.shipping.urls")),
    path("", include("src.interface.api.tax.urls")),
    path("", include("src.interface.api.inventory.urls")),
]

urlpatterns = [
    path("api/v1/", include((api_v1_patterns, "api-v1"))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
