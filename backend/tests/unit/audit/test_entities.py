"""Unit tests for the audit domain entities.

``AuditEntry`` and ``FieldChange`` are pure-Python value objects: they validate
their own shape so a malformed audit record can never be constructed, regardless
of which context emits it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.domain.audit.entities import AuditEntry, FieldChange
from src.domain.audit.exceptions import InvalidAuditEntryError

_NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)


def _entry(**overrides: object) -> AuditEntry:
    defaults: dict[str, object] = {
        "action": "channel.created",
        "resource_type": "channel",
        "resource_id": "1",
        "occurred_at": _NOW,
    }
    defaults.update(overrides)
    return AuditEntry(**defaults)  # type: ignore[arg-type]


class TestFieldChange:
    def test_captures_before_and_after_values(self) -> None:
        change = FieldChange(field="is_active", before=True, after=False)

        assert change.field == "is_active"
        assert change.before is True
        assert change.after is False

    def test_before_and_after_default_to_none(self) -> None:
        # A creation has no "before"; only an "after" value.
        change = FieldChange(field="slug", after="coffee")

        assert change.before is None
        assert change.after == "coffee"

    @pytest.mark.parametrize("bad_field", ["", "  ", "Is_Active", "1field", "has space"])
    def test_rejects_a_malformed_field_name(self, bad_field: str) -> None:
        with pytest.raises(InvalidAuditEntryError):
            FieldChange(field=bad_field, after="x")

    def test_is_immutable(self) -> None:
        change = FieldChange(field="is_active", after=True)

        with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises FrozenInstanceError
            change.after = False  # type: ignore[misc]


class TestAuditEntry:
    def test_builds_a_valid_entry(self) -> None:
        entry = _entry(
            actor="42",
            changes=(FieldChange(field="is_active", before=True, after=False),),
        )

        assert entry.action == "channel.created"
        assert entry.resource_type == "channel"
        assert entry.resource_id == "1"
        assert entry.actor == "42"
        assert entry.occurred_at == _NOW
        assert entry.changes[0].field == "is_active"

    def test_actor_and_changes_are_optional(self) -> None:
        # A system-initiated change has no human actor and need not list fields.
        entry = _entry()

        assert entry.actor is None
        assert entry.changes == ()

    @pytest.mark.parametrize(
        "bad_action",
        ["", "created", "Channel.Created", "channel.", ".created", "channel created"],
    )
    def test_action_must_be_a_dotted_namespaced_event(self, bad_action: str) -> None:
        # The convention is "<context>.<event>" so the trail is greppable by area.
        with pytest.raises(InvalidAuditEntryError):
            _entry(action=bad_action)

    @pytest.mark.parametrize("bad_type", ["", "Channel", "1resource", "user profile"])
    def test_resource_type_must_be_an_identifier(self, bad_type: str) -> None:
        with pytest.raises(InvalidAuditEntryError):
            _entry(resource_type=bad_type)

    @pytest.mark.parametrize("bad_id", ["", "   "])
    def test_resource_id_must_not_be_blank(self, bad_id: str) -> None:
        with pytest.raises(InvalidAuditEntryError):
            _entry(resource_id=bad_id)

    def test_actor_when_present_must_not_be_blank(self) -> None:
        with pytest.raises(InvalidAuditEntryError):
            _entry(actor="   ")

    def test_occurred_at_must_be_timezone_aware(self) -> None:
        # A naive timestamp is ambiguous across zones; an audit trail cannot afford
        # that. Only tz-aware instants are accepted.
        naive = datetime(2026, 6, 28, 12, 0)  # intentionally naive (no tzinfo)
        with pytest.raises(InvalidAuditEntryError):
            _entry(occurred_at=naive)

    def test_accepts_a_non_utc_aware_timestamp(self) -> None:
        tehran = timezone(timedelta(hours=3, minutes=30))
        entry = _entry(occurred_at=datetime(2026, 6, 28, 15, 30, tzinfo=tehran))

        assert entry.occurred_at.tzinfo is not None
