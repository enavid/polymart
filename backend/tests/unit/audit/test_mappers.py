"""Unit tests for the audit change mappers (pure, no DB)."""

from __future__ import annotations

from src.domain.audit.entities import FieldChange
from src.infrastructure.audit.mappers import changes_from_json, changes_to_json


class TestChangesMapping:
    def test_round_trips_through_the_stored_shape(self) -> None:
        changes = (
            FieldChange(field="is_active", before=True, after=False),
            FieldChange(field="role", after="channel_admin"),
        )

        restored = changes_from_json(changes_to_json(changes))

        assert restored == changes

    def test_empty_changes_round_trip(self) -> None:
        assert changes_from_json(changes_to_json(())) == ()
