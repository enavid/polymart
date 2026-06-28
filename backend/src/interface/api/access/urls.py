"""URL patterns for the access-administration slice."""

from __future__ import annotations

from django.urls import path

from src.interface.api.access.views import ChannelGrantView, RoleAssignmentView

urlpatterns = [
    path("access/role-assignments/", RoleAssignmentView.as_view(), name="access-role-assignment"),
    path("access/channel-grants/", ChannelGrantView.as_view(), name="access-channel-grant"),
]
