"""Unit tests for the ListAuditEntries read use case (no DB).

Pins the paging policy -- a default page size and a hard ceiling -- and that
filters are forwarded verbatim to the query port.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.audit.ports import AuditQuery
from src.application.audit.read import DEFAULT_LIMIT, MAX_LIMIT, ListAuditEntries
from src.domain.audit.entities import AuditEntry


class FakeAuditQuery(AuditQuery):
    """Records the arguments it was called with and returns a canned result."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.result: Sequence[AuditEntry] = []

    def list_recent(
        self,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        action: str | None = None,
        limit: int,
    ) -> Sequence[AuditEntry]:
        self.calls.append(
            {
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                "limit": limit,
            }
        )
        return self.result


class TestListAuditEntries:
    def test_uses_the_default_limit_when_unset_or_invalid(self) -> None:
        query = FakeAuditQuery()
        use_case = ListAuditEntries(query)

        use_case.execute(limit=None)
        use_case.execute(limit=0)
        use_case.execute(limit=-5)

        assert [call["limit"] for call in query.calls] == [DEFAULT_LIMIT] * 3

    def test_caps_an_excessive_limit_at_the_maximum(self) -> None:
        query = FakeAuditQuery()

        ListAuditEntries(query).execute(limit=10_000)

        assert query.calls[0]["limit"] == MAX_LIMIT

    def test_passes_a_reasonable_limit_through(self) -> None:
        query = FakeAuditQuery()

        ListAuditEntries(query).execute(limit=10)

        assert query.calls[0]["limit"] == 10

    def test_forwards_the_filters(self) -> None:
        query = FakeAuditQuery()

        ListAuditEntries(query).execute(
            resource_type="user", resource_id="7", action="access.role_assigned", limit=5
        )

        call = query.calls[0]
        assert call["resource_type"] == "user"
        assert call["resource_id"] == "7"
        assert call["action"] == "access.role_assigned"
