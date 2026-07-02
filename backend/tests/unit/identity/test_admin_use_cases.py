"""Unit tests for the administrative user-management use cases (fakes, no DB)."""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.identity.admin_use_cases import (
    AdminCreateUser,
    InvalidUserPageError,
    ListUserAccounts,
)
from src.application.identity.ports import UserAccount, UserDirectory
from src.domain.audit.entities import FieldChange
from src.domain.identity.exceptions import InvalidPhoneNumberError, UserAlreadyExistsError


class FakeUserDirectory(UserDirectory):
    """An in-memory account store recording the accounts it creates."""

    def __init__(self) -> None:
        self._by_id: dict[int, UserAccount] = {}
        self._by_phone: dict[str, int] = {}
        self._sequence = 0
        self.created_passwords: dict[int, str] = {}

    def exists(self, phone_number: str) -> bool:
        return phone_number in self._by_phone

    def create(
        self,
        phone_number: str,
        *,
        password: str,
        full_name: str,
        email: str,
        is_staff: bool = False,
    ) -> int:
        if phone_number in self._by_phone:
            raise UserAlreadyExistsError(phone_number)
        self._sequence += 1
        self._by_phone[phone_number] = self._sequence
        self._by_id[self._sequence] = UserAccount(
            id=self._sequence,
            phone_number=phone_number,
            full_name=full_name,
            email=email,
            is_staff=is_staff,
            is_active=True,
        )
        self.created_passwords[self._sequence] = password
        return self._sequence

    def set_password(self, phone_number: str, new_password: str) -> int:  # pragma: no cover
        raise NotImplementedError

    def list_accounts(self, *, limit: int, offset: int) -> tuple[tuple[UserAccount, ...], int]:
        ordered = [self._by_id[k] for k in sorted(self._by_id)]
        return tuple(ordered[offset : offset + limit]), len(ordered)

    def get_account(self, user_id: int) -> UserAccount:
        return self._by_id[user_id]


class RecordingAudit(AuditRecorder):
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: tuple[FieldChange, ...] = (),
    ) -> None:
        self.records.append(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "actor": actor,
                "changes": changes,
            }
        )


def _seed(directory: FakeUserDirectory, count: int) -> None:
    for i in range(count):
        directory.create(f"0912000000{i}", password="pw", full_name=f"User {i}", email="")


class TestListUserAccounts:
    def test_returns_a_page_with_the_total_count(self) -> None:
        directory = FakeUserDirectory()
        _seed(directory, 3)

        page = ListUserAccounts(directory).execute(limit=2, offset=0)

        assert len(page.items) == 2
        assert page.total == 3

    def test_windows_by_offset(self) -> None:
        directory = FakeUserDirectory()
        _seed(directory, 3)

        page = ListUserAccounts(directory).execute(limit=2, offset=2)

        assert len(page.items) == 1
        assert page.total == 3

    def test_logs_a_structured_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        directory = FakeUserDirectory()
        _seed(directory, 1)
        # Assert against the logger directly rather than structlog.capture_logs:
        # the module logger is cached (cache_logger_on_first_use=True), so once an
        # integration test has used it under the real config, capture_logs can no
        # longer intercept it -- a global-state order dependency. A recording double
        # verifies the event name and fields deterministically.
        events: list[tuple[str, dict[str, object]]] = []

        class _RecordingLogger:
            def info(self, event: str, **fields: object) -> None:
                events.append((event, fields))

        monkeypatch.setattr("src.application.identity.admin_use_cases.logger", _RecordingLogger())

        ListUserAccounts(directory).execute()

        assert events == [("user_accounts_listed", {"count": 1, "returned": 1})]

    @pytest.mark.parametrize("limit", [0, -1, 101])
    def test_rejects_an_out_of_range_limit(self, limit: int) -> None:
        with pytest.raises(InvalidUserPageError):
            ListUserAccounts(FakeUserDirectory()).execute(limit=limit)

    def test_rejects_a_negative_offset(self) -> None:
        with pytest.raises(InvalidUserPageError):
            ListUserAccounts(FakeUserDirectory()).execute(offset=-1)


class TestAdminCreateUser:
    def test_creates_and_returns_the_account(self) -> None:
        directory = FakeUserDirectory()

        account = AdminCreateUser(directory, RecordingAudit()).execute(
            phone_number_raw="09120000001", password="pw", full_name="Sara", is_staff=True
        )

        assert account.full_name == "Sara"
        assert account.is_staff is True
        # The phone number is canonicalised by the domain value object.
        assert account.phone_number.startswith("+98")

    def test_records_an_audit_event(self) -> None:
        directory = FakeUserDirectory()
        audit = RecordingAudit()

        account = AdminCreateUser(directory, audit).execute(
            phone_number_raw="09120000001", password="pw", is_staff=True, actor="7"
        )

        record = audit.records[-1]
        assert record["action"] == "user.created"
        assert record["resource_type"] == "user"
        assert record["resource_id"] == str(account.id)
        assert record["actor"] == "7"

    def test_never_logs_the_password(self) -> None:
        directory = FakeUserDirectory()

        with capture_logs() as logs:
            AdminCreateUser(directory, RecordingAudit()).execute(
                phone_number_raw="09120000001", password="super-secret"
            )

        assert not any("super-secret" in str(event) for event in logs)

    def test_a_duplicate_phone_raises(self) -> None:
        directory = FakeUserDirectory()
        audit = RecordingAudit()
        AdminCreateUser(directory, audit).execute(phone_number_raw="09120000001", password="pw")

        with pytest.raises(UserAlreadyExistsError):
            AdminCreateUser(directory, audit).execute(phone_number_raw="09120000001", password="pw")

    def test_an_invalid_phone_raises(self) -> None:
        with pytest.raises(InvalidPhoneNumberError):
            AdminCreateUser(FakeUserDirectory(), RecordingAudit()).execute(
                phone_number_raw="not-a-phone", password="pw"
            )
