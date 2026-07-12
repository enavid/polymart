"""URL patterns for the access-administration slice."""

from __future__ import annotations

from django.urls import path

from src.interface.api.access.views import (
    ChannelGrantView,
    RoleAssignmentView,
    StockSourceGrantView,
    UserAdminView,
)

urlpatterns = [
    path("access/users/", UserAdminView.as_view(), name="access-user-admin"),
    path("access/role-assignments/", RoleAssignmentView.as_view(), name="access-role-assignment"),
    path("access/channel-grants/", ChannelGrantView.as_view(), name="access-channel-grant"),
    path(
        "access/stock-source-grants/",
        StockSourceGrantView.as_view(),
        name="access-stock-source-grant",
    ),
]
