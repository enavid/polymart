"""Unit tests for the catalog use cases.

Exercised against an in-memory fake repository and a fake audit recorder: no
Django, no database. Business orchestration is testable in isolation.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import AttributeRepository
from src.application.catalog.use_cases import (
    AttributeChoiceInput,
    CreateAttribute,
    CreateAttributeCommand,
    GetAttribute,
    ListAttributes,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Attribute
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    AttributeChoicesRequiredError,
    AttributeNotFoundError,
    InvalidAttributeInputTypeError,
)


class FakeAttributeRepository(AttributeRepository):
    """In-memory stand-in keyed by code, mimicking the real repo's contract."""

    def __init__(self) -> None:
        self._by_code: dict[str, Attribute] = {}
        self._sequence = 0

    def add(self, attribute: Attribute) -> Attribute:
        code = attribute.code.value
        if code in self._by_code:
            raise AttributeAlreadyExistsError(code)
        self._sequence += 1
        attribute.id = self._sequence
        self._by_code[code] = attribute
        return attribute

    def get_by_code(self, code: str) -> Attribute:
        try:
            return self._by_code[code]
        except KeyError:
            raise AttributeNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:
        return code in self._by_code

    def list_all(self) -> list[Attribute]:
        return [self._by_code[c] for c in sorted(self._by_code)]


class RecordedAudit:
    def __init__(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None,
        changes: tuple[FieldChange, ...],
    ) -> None:
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.actor = actor
        self.changes = changes


class FakeAuditRecorder(AuditRecorder):
    def __init__(self) -> None:
        self.calls: list[RecordedAudit] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: Sequence[FieldChange] = (),
    ) -> None:
        self.calls.append(RecordedAudit(action, resource_type, resource_id, actor, tuple(changes)))


@pytest.fixture
def repo() -> FakeAttributeRepository:
    return FakeAttributeRepository()


@pytest.fixture
def audit() -> FakeAuditRecorder:
    return FakeAuditRecorder()


def _text_command(code: str = "origin", name: str = "Origin") -> CreateAttributeCommand:
    return CreateAttributeCommand(code=code, name=name, input_type="plain_text")


class TestCreateAttribute:
    def test_persists_and_returns_an_attribute_with_an_identity(
        self, repo: FakeAttributeRepository, audit: FakeAuditRecorder
    ) -> None:
        attribute = CreateAttribute(repo, audit).execute(_text_command())

        assert attribute.id is not None
        assert attribute.code.value == "origin"
        assert attribute.input_type.value == "plain_text"
        assert repo.exists_by_code("origin")

    def test_creates_a_dropdown_with_its_choices(
        self, repo: FakeAttributeRepository, audit: FakeAuditRecorder
    ) -> None:
        attribute = CreateAttribute(repo, audit).execute(
            CreateAttributeCommand(
                code="roast-level",
                name="Roast level",
                input_type="dropdown",
                choices=(
                    AttributeChoiceInput(value="light", label="Light"),
                    AttributeChoiceInput(value="dark", label="Dark"),
                ),
            )
        )

        assert [c.value for c in attribute.choices] == ["light", "dark"]

    def test_rejects_an_unknown_input_type(
        self, repo: FakeAttributeRepository, audit: FakeAuditRecorder
    ) -> None:
        with pytest.raises(InvalidAttributeInputTypeError):
            CreateAttribute(repo, audit).execute(
                CreateAttributeCommand(code="origin", name="Origin", input_type="rich_text")
            )

        assert repo.list_all() == []

    def test_rejects_a_duplicate_code(
        self, repo: FakeAttributeRepository, audit: FakeAuditRecorder
    ) -> None:
        use_case = CreateAttribute(repo, audit)
        use_case.execute(_text_command())

        with pytest.raises(AttributeAlreadyExistsError):
            use_case.execute(_text_command(name="Origin Again"))

    def test_does_not_persist_a_dropdown_without_choices(
        self, repo: FakeAttributeRepository, audit: FakeAuditRecorder
    ) -> None:
        with pytest.raises(AttributeChoicesRequiredError):
            CreateAttribute(repo, audit).execute(
                CreateAttributeCommand(code="roast-level", name="Roast", input_type="dropdown")
            )

        assert repo.list_all() == []

    def test_writes_a_durable_audit_entry(
        self, repo: FakeAttributeRepository, audit: FakeAuditRecorder
    ) -> None:
        attribute = CreateAttribute(repo, audit).execute(_text_command(), actor="operator")

        assert len(audit.calls) == 1
        call = audit.calls[0]
        assert call.action == "attribute.created"
        assert call.resource_type == "attribute"
        assert call.resource_id == str(attribute.id)
        assert call.actor == "operator"
        recorded = {change.field: change.after for change in call.changes}
        assert recorded["code"] == "origin"
        assert recorded["input_type"] == "plain_text"

    def test_records_the_acting_user_in_the_log(
        self, repo: FakeAttributeRepository, audit: FakeAuditRecorder
    ) -> None:
        with capture_logs() as logs:
            CreateAttribute(repo, audit).execute(_text_command(), actor="operator")

        events = [entry for entry in logs if entry["event"] == "attribute_created"]
        assert events and events[0]["actor"] == "operator"

    def test_does_not_audit_a_rejected_duplicate(
        self, repo: FakeAttributeRepository, audit: FakeAuditRecorder
    ) -> None:
        use_case = CreateAttribute(repo, audit)
        use_case.execute(_text_command())

        with pytest.raises(AttributeAlreadyExistsError):
            use_case.execute(_text_command())

        assert len(audit.calls) == 1


class TestGetAttribute:
    def test_returns_the_requested_attribute(
        self, repo: FakeAttributeRepository, audit: FakeAuditRecorder
    ) -> None:
        CreateAttribute(repo, audit).execute(_text_command())

        attribute = GetAttribute(repo).execute(code="origin")

        assert attribute.code.value == "origin"

    def test_raises_when_missing(self, repo: FakeAttributeRepository) -> None:
        with pytest.raises(AttributeNotFoundError):
            GetAttribute(repo).execute(code="ghost")


class TestListAttributes:
    def test_returns_all_attributes_sorted_by_code(
        self, repo: FakeAttributeRepository, audit: FakeAuditRecorder
    ) -> None:
        create = CreateAttribute(repo, audit)
        create.execute(_text_command(code="origin", name="Origin"))
        create.execute(_text_command(code="brand", name="Brand"))

        attributes = ListAttributes(repo).execute()

        assert [a.code.value for a in attributes] == ["brand", "origin"]
