"""Composition root for the channel slice.

The only place that wires concrete infrastructure adapters into the use cases.
Views depend on these factories, never on the infrastructure layer directly.
"""
from __future__ import annotations

from src.application.channel.use_cases import (
    CreateChannel,
    GetChannel,
    ListChannels,
    SetChannelStatus,
)
from src.infrastructure.channel.repositories import DjangoChannelRepository


def build_create_channel() -> CreateChannel:
    return CreateChannel(DjangoChannelRepository())


def build_set_channel_status() -> SetChannelStatus:
    return SetChannelStatus(DjangoChannelRepository())


def build_get_channel() -> GetChannel:
    return GetChannel(DjangoChannelRepository())


def build_list_channels() -> ListChannels:
    return ListChannels(DjangoChannelRepository())
