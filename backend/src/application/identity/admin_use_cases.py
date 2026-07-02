"""Administrative user-management use cases (access-admin surface).

Distinct from the OTP self-service flows in ``use_cases.py``: these are performed
by an administrator (gated by ``manage_access`` at the transport layer) to list the
accounts an admin might assign roles/grants to, and to create an account directly
without the OTP round-trip a self-registering user goes through.

They orchestrate the ``UserDirectory`` port and audit every account creation; they
hold no transport or framework detail and never log the password (a secret) or the
phone number (PII).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.application.audit.ports import AuditRecorder
from src.application.identity.ports import UserAccount, UserDirectory
from src.domain.audit.entities import FieldChange
from src.domain.identity.value_objects import PhoneNumber

logger = structlog.get_logger(__name__)

# Pagination bounds for the account listing, mirroring the catalog read window so a
# caller cannot ask for an unbounded page.
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100

_ACTION_USER_CREATED = "user.created"
_RESOURCE_USER = "user"


class InvalidUserPageError(Exception):
    """Raised when the requested account page window is out of range."""


@dataclass(frozen=True)
class UserAccountPage:
    """One page of user accounts plus the full account count (for pagination)."""

    items: tuple[UserAccount, ...]
    total: int


class ListUserAccounts:
    """List user accounts for the access-admin user picker (paged, ordered by id)."""

    def __init__(self, users: UserDirectory) -> None:
        self._users = users

    def execute(self, *, limit: int = DEFAULT_PAGE_LIMIT, offset: int = 0) -> UserAccountPage:
        limit, offset = self._validated_window(limit, offset)
        items, total = self._users.list_accounts(limit=limit, offset=offset)
        # An admin, low-frequency action (unlike high-frequency public storefront
        # reads, which stay debug) -- info keeps it in the operational trail.
        logger.info("user_accounts_listed", count=total, returned=len(items))
        return UserAccountPage(items=tuple(items), total=total)

    @staticmethod
    def _validated_window(limit: int, offset: int) -> tuple[int, int]:
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise InvalidUserPageError(f"limit must be between 1 and {MAX_PAGE_LIMIT}: {limit}")
        if offset < 0:
            raise InvalidUserPageError(f"offset must not be negative: {offset}")
        return limit, offset


class AdminCreateUser:
    """Create an account directly (admin), bypassing the OTP self-service flow.

    The phone number is validated and canonicalised by the domain value object; a
    duplicate surfaces as ``UserAlreadyExistsError`` from the directory. The creation
    is audited (never the password), and the created account projection is returned.
    """

    def __init__(self, users: UserDirectory, audit: AuditRecorder) -> None:
        self._users = users
        self._audit = audit

    def execute(
        self,
        *,
        phone_number_raw: str,
        password: str,
        full_name: str = "",
        email: str = "",
        is_staff: bool = False,
        actor: str | None = None,
    ) -> UserAccount:
        phone = PhoneNumber(phone_number_raw).value
        user_id = self._users.create(
            phone, password=password, full_name=full_name, email=email, is_staff=is_staff
        )
        logger.info("user_created_by_admin", user_id=user_id, is_staff=is_staff, actor=actor)
        self._audit.record(
            action=_ACTION_USER_CREATED,
            resource_type=_RESOURCE_USER,
            resource_id=str(user_id),
            actor=actor,
            changes=(FieldChange(field="is_staff", after=is_staff),),
        )
        return self._users.get_account(user_id)
