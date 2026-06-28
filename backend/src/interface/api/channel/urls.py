"""URL patterns for the channel slice."""
from __future__ import annotations

from django.urls import path

from src.interface.api.channel.views import ChannelDetailView, ChannelListCreateView

urlpatterns = [
    path("channels/", ChannelListCreateView.as_view(), name="channel-list"),
    path(
        "channels/<slug:slug>/",
        ChannelDetailView.as_view(),
        name="channel-detail",
    ),
]
