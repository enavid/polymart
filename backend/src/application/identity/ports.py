"""Ports (interfaces) for the identity OTP use cases.

The application layer depends only on these abstractions. Concrete adapters
(Django ORM, HMAC hashing, SMS gateway, system clock) live in infrastructure and
are injected at the composition root, so the dependency rule keeps pointing
inward and the use cases stay testable against fakes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.identity.entities import OtpChallenge
from src.domain.identity.enums import OtpPurpose


class OtpRepository(ABC):
    """Persistence boundary for one-time-code challenges."""

    @abstractmethod
    def save(self, challenge: OtpChallenge) -> OtpChallenge:
        """Persist a new challenge or changes to an existing one, returning it
        with its assigned ``id``."""

    @abstractmethod
    def get_latest(self, phone_number: str, purpose: OtpPurpose) -> OtpChallenge | None:
        """Return the most recently created challenge for this phone and purpose,
        or ``None`` if none exists."""


class CodeGenerator(ABC):
    """Source of fresh one-time codes."""

    @abstractmethod
    def generate(self) -> str:
        """Return a new numeric code as a string."""


class CodeHasher(ABC):
    """One-way transform used to store and compare codes without keeping them."""

    @abstractmethod
    def hash(self, code: str) -> str:
        """Return the storable hash of a code."""

    @abstractmethod
    def verify(self, code: str, code_hash: str) -> bool:
        """Return whether ``code`` matches ``code_hash`` (constant-time)."""


class SmsSender(ABC):
    """Delivery boundary for sending a code to a phone (Iranian SMS gateway)."""

    @abstractmethod
    def send_otp(self, phone_number: str, code: str) -> None:
        """Deliver the code to the phone number."""


class Clock(ABC):
    """Source of the current time, injected so expiry/cooldown are testable."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current timezone-aware time."""


class UserDirectory(ABC):
    """Boundary for the user accounts the OTP flows create and update.

    Returns plain identifiers, never ORM instances, so the application layer
    stays free of framework types.
    """

    @abstractmethod
    def exists(self, phone_number: str) -> bool:
        """Return whether an account already exists for this phone number."""

    @abstractmethod
    def create(self, phone_number: str, *, password: str, full_name: str, email: str) -> int:
        """Create an account and return its id.

        Raises ``UserAlreadyExistsError`` if the phone number is already taken.
        """

    @abstractmethod
    def set_password(self, phone_number: str, new_password: str) -> int:
        """Replace the account's password and return its id.

        Raises ``UserNotFoundError`` if no account exists for the phone number.
        """
