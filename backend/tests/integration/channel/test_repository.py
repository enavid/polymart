"""Integration tests for the Django channel repository (real database).

These verify the infrastructure adapter honours the port contract, including the
translation of ORM failures into domain exceptions.
"""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.application.channel.use_cases import CreateChannel, CreateChannelCommand
from src.domain.channel.entities import Channel
from src.domain.channel.exceptions import ChannelAlreadyExistsError, ChannelNotFoundError
from src.domain.channel.value_objects import ChannelSlug, Currency
from src.infrastructure.channel.models import ChannelModel
from src.infrastructure.channel.repositories import DjangoChannelRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _entity(slug: str = "coffee", *, is_active: bool = True) -> Channel:
    return Channel(
        slug=ChannelSlug(slug),
        name=f"{slug} store",
        currency=Currency("IRR"),
        is_active=is_active,
    )


def test_add_persists_and_assigns_an_identity() -> None:
    repo = DjangoChannelRepository()

    channel = repo.add(_entity())

    assert channel.id is not None
    assert ChannelModel.objects.filter(slug="coffee").count() == 1
    assert str(ChannelModel.objects.get(slug="coffee")) == "coffee"


def test_add_translates_unique_violation_into_domain_error() -> None:
    repo = DjangoChannelRepository()
    repo.add(_entity())

    with pytest.raises(ChannelAlreadyExistsError):
        repo.add(_entity())


def test_add_logs_the_lost_insert_race() -> None:
    # The unique-violation path is how a concurrent insert is detected once the
    # use case's pre-check has been overtaken; it must leave an audit trail.
    repo = DjangoChannelRepository()
    repo.add(_entity())

    with capture_logs() as logs, pytest.raises(ChannelAlreadyExistsError):
        repo.add(_entity())

    events = [entry for entry in logs if entry["event"] == "channel_insert_race_lost"]
    assert events, "expected the lost-race to be logged"
    assert events[0]["slug"] == "coffee"


def test_get_by_slug_round_trips_the_entity() -> None:
    repo = DjangoChannelRepository()
    repo.add(_entity())

    fetched = repo.get_by_slug("coffee")

    assert fetched.slug.value == "coffee"
    assert fetched.currency == Currency("IRR")
    assert fetched.is_active is True


def test_get_by_slug_raises_for_unknown_channel() -> None:
    with pytest.raises(ChannelNotFoundError):
        DjangoChannelRepository().get_by_slug("ghost")


def test_exists_by_slug_reflects_persistence() -> None:
    repo = DjangoChannelRepository()
    assert repo.exists_by_slug("coffee") is False

    repo.add(_entity())

    assert repo.exists_by_slug("coffee") is True


def test_list_all_is_ordered_by_slug() -> None:
    repo = DjangoChannelRepository()
    repo.add(_entity("tea"))
    repo.add(_entity("coffee"))

    slugs = [c.slug.value for c in repo.list_all()]

    assert slugs == ["coffee", "tea"]


def test_update_persists_status_changes() -> None:
    repo = DjangoChannelRepository()
    repo.add(_entity())
    channel = repo.get_by_slug("coffee")
    channel.deactivate()

    repo.update(channel)

    assert repo.get_by_slug("coffee").is_active is False


def test_update_raises_for_unknown_channel() -> None:
    with pytest.raises(ChannelNotFoundError):
        DjangoChannelRepository().update(_entity("ghost"))


def test_create_channel_use_case_with_real_repository() -> None:
    use_case = CreateChannel(DjangoChannelRepository())

    channel = use_case.execute(CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR"))

    assert channel.id is not None
    assert ChannelModel.objects.get(slug="coffee").currency_code == "IRR"
