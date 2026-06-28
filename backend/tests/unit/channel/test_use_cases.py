"""Unit tests for the channel use cases.

The use cases are exercised against an in-memory fake repository: no Django, no
database. This is the payoff of the dependency rule -- business orchestration is
testable in isolation and at speed.
"""
from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.application.channel.ports import ChannelRepository
from src.application.channel.use_cases import (
    CreateChannel,
    CreateChannelCommand,
    GetChannel,
    ListChannels,
    SetChannelStatus,
)
from src.domain.channel.entities import Channel
from src.domain.channel.exceptions import (
    ChannelAlreadyExistsError,
    ChannelNotFoundError,
    InvalidCurrencyCodeError,
)


class FakeChannelRepository(ChannelRepository):
    """In-memory stand-in keyed by slug, mimicking the real repo's contract."""

    def __init__(self) -> None:
        self._by_slug: dict[str, Channel] = {}
        self._sequence = 0

    def add(self, channel: Channel) -> Channel:
        slug = channel.slug.value
        if slug in self._by_slug:
            raise ChannelAlreadyExistsError(slug)
        self._sequence += 1
        channel.id = self._sequence
        self._by_slug[slug] = channel
        return channel

    def get_by_slug(self, slug: str) -> Channel:
        try:
            return self._by_slug[slug]
        except KeyError:
            raise ChannelNotFoundError(slug) from None

    def exists_by_slug(self, slug: str) -> bool:
        return slug in self._by_slug

    def list_all(self) -> list[Channel]:
        return [self._by_slug[s] for s in sorted(self._by_slug)]

    def update(self, channel: Channel) -> Channel:
        slug = channel.slug.value
        if slug not in self._by_slug:
            raise ChannelNotFoundError(slug)
        self._by_slug[slug] = channel
        return channel


@pytest.fixture
def repo() -> FakeChannelRepository:
    return FakeChannelRepository()


class TestCreateChannel:
    def test_persists_and_returns_a_channel_with_an_identity(
        self, repo: FakeChannelRepository
    ) -> None:
        use_case = CreateChannel(repo)

        channel = use_case.execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        assert channel.id is not None
        assert channel.slug.value == "coffee"
        assert channel.currency.code == "IRR"
        assert channel.is_active is True
        assert repo.exists_by_slug("coffee")

    def test_rejects_a_duplicate_slug(self, repo: FakeChannelRepository) -> None:
        use_case = CreateChannel(repo)
        use_case.execute(CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR"))

        with pytest.raises(ChannelAlreadyExistsError):
            use_case.execute(CreateChannelCommand(name="Other", slug="coffee", currency="USD"))

    def test_does_not_persist_when_the_currency_is_invalid(
        self, repo: FakeChannelRepository
    ) -> None:
        use_case = CreateChannel(repo)

        with pytest.raises(InvalidCurrencyCodeError):
            use_case.execute(CreateChannelCommand(name="Coffee", slug="coffee", currency="toman"))

        assert repo.list_all() == []

    def test_can_create_an_initially_inactive_channel(self, repo: FakeChannelRepository) -> None:
        use_case = CreateChannel(repo)

        channel = use_case.execute(
            CreateChannelCommand(name="Draft", slug="draft", currency="IRR", is_active=False)
        )

        assert channel.is_active is False

    def test_records_the_acting_user_in_the_audit_event(
        self, repo: FakeChannelRepository
    ) -> None:
        # Channel mutations gate currency/pricing; the audit trail must say who
        # made the change, not just that it happened.
        with capture_logs() as logs:
            CreateChannel(repo).execute(
                CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR"),
                actor="operator",
            )

        events = [entry for entry in logs if entry["event"] == "channel_created"]
        assert events and events[0]["actor"] == "operator"


class TestSetChannelStatus:
    def test_deactivates_an_existing_channel(self, repo: FakeChannelRepository) -> None:
        CreateChannel(repo).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        channel = SetChannelStatus(repo).execute(slug="coffee", active=False)

        assert channel.is_active is False
        assert repo.get_by_slug("coffee").is_active is False

    def test_is_idempotent(self, repo: FakeChannelRepository) -> None:
        CreateChannel(repo).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        SetChannelStatus(repo).execute(slug="coffee", active=True)
        channel = SetChannelStatus(repo).execute(slug="coffee", active=True)

        assert channel.is_active is True

    def test_raises_when_the_channel_is_unknown(self, repo: FakeChannelRepository) -> None:
        with pytest.raises(ChannelNotFoundError):
            SetChannelStatus(repo).execute(slug="ghost", active=False)

    def test_records_the_acting_user_in_the_audit_event(
        self, repo: FakeChannelRepository
    ) -> None:
        CreateChannel(repo).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        with capture_logs() as logs:
            SetChannelStatus(repo).execute(slug="coffee", active=False, actor="operator")

        events = [entry for entry in logs if entry["event"] == "channel_status_changed"]
        assert events and events[0]["actor"] == "operator"


class TestGetChannel:
    def test_returns_the_requested_channel(self, repo: FakeChannelRepository) -> None:
        CreateChannel(repo).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        channel = GetChannel(repo).execute(slug="coffee")

        assert channel.slug.value == "coffee"

    def test_raises_when_missing(self, repo: FakeChannelRepository) -> None:
        with pytest.raises(ChannelNotFoundError):
            GetChannel(repo).execute(slug="ghost")


class TestListChannels:
    def test_returns_all_channels_sorted_by_slug(self, repo: FakeChannelRepository) -> None:
        create = CreateChannel(repo)
        create.execute(CreateChannelCommand(name="Tea", slug="tea", currency="IRR"))
        create.execute(CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR"))

        channels = ListChannels(repo).execute()

        assert [c.slug.value for c in channels] == ["coffee", "tea"]

    def test_can_filter_to_active_channels_only(self, repo: FakeChannelRepository) -> None:
        create = CreateChannel(repo)
        create.execute(CreateChannelCommand(name="Tea", slug="tea", currency="IRR"))
        create.execute(
            CreateChannelCommand(name="Draft", slug="draft", currency="IRR", is_active=False)
        )

        channels = ListChannels(repo).execute(only_active=True)

        assert [c.slug.value for c in channels] == ["tea"]
