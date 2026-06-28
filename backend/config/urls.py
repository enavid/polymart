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
