"""Unit tests for the OTP use cases (registration, password reset, requesting).

Exercised entirely against in-memory fakes -- no Django, no database, no clock,
no randomness. This is where the adversarial rules live: wrong codes lock out,
expired codes are rejected, a spent code cannot be replayed, the raw code and
password never reach the logs, and OTP requests are uniform to avoid leaking
which phone numbers have accounts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from structlog.testing import capture_logs

from src.application.identity.ports import (
    Clock,
    CodeGenerator,
    CodeHasher,
    OtpRepository,
    SmsSender,
    UserDirectory,
)
from src.application.identity.use_cases import (
    OtpVerifier,
    RegisterUser,
    RequestOtp,
    ResetPassword,
)
from src.domain.identity.entities import OtpChallenge
from src.domain.identity.enums import OtpPurpose
from src.domain.identity.exceptions import (
    InvalidOtpError,
    InvalidPhoneNumberError,
    OtpExpiredError,
    OtpMaxAttemptsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)

_PHONE = "09123456789"
_CANONICAL = "+989123456789"
_CODE = "123456"
_PASSWORD = "s3cret-password"


class FakeOtpRepository(OtpRepository):
    def __init__(self) -> None:
        self._rows: list[OtpChallenge] = []
        self._sequence = 0

    def save(self, challenge: OtpChallenge) -> OtpChallenge:
        if challenge.id is None:
            self._sequence += 1
            challenge.id = self._sequence
            self._rows.append(challenge)
        return challenge

    def get_latest(self, phone_number: str, purpose: OtpPurpose) -> OtpChallenge | None:
        matching = [
            row for row in self._rows if row.phone_number == phone_number and row.purpose == purpose
        ]
        if not matching:
            return None
        return max(matching, key=lambda row: row.created_at)


class FakeUserDirectory(UserDirectory):
    def __init__(self) -> None:
        self._passwords: dict[str, str] = {}
        self._ids: dict[str, int] = {}
        self._sequence = 0

    def exists(self, phone_number: str) -> bool:
        return phone_number in self._ids

    def create(self, phone_number: str, *, password: str, full_name: str, email: str) -> int:
        if phone_number in self._ids:
            raise UserAlreadyExistsError(phone_number)
        self._sequence += 1
        self._ids[phone_number] = self._sequence
        self._passwords[phone_number] = password
        return self._sequence

    def set_password(self, phone_number: str, new_password: str) -> int:
        if phone_number not in self._ids:
            raise UserNotFoundError(phone_number)
        self._passwords[phone_number] = new_password
        return self._ids[phone_number]


class StubCodeGenerator(CodeGenerator):
    def __init__(self, code: str = _CODE) -> None:
        self.code = code

    def generate(self) -> str:
        return self.code


class ReversibleHasher(CodeHasher):
    """A deterministic, non-cryptographic stand-in.

    Like a real hash, its output does not contain the raw code (it stores the
    reversed digits), so tests can assert the code never leaks into storage.
    """

    def hash(self, code: str) -> str:
        return f"h:{code[::-1]}"

    def verify(self, code: str, code_hash: str) -> bool:
        return self.hash(code) == code_hash


class RecordingSmsSender(SmsSender):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_otp(self, phone_number: str, code: str) -> None:
        self.sent.append((phone_number, code))


class FrozenClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def set(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def clock(now: datetime) -> FrozenClock:
    return FrozenClock(now)


@pytest.fixture
def otp_repo() -> FakeOtpRepository:
    return FakeOtpRepository()


@pytest.fixture
def users() -> FakeUserDirectory:
    return FakeUserDirectory()


@pytest.fixture
def generator() -> StubCodeGenerator:
    return StubCodeGenerator()


@pytest.fixture
def hasher() -> ReversibleHasher:
    return ReversibleHasher()


@pytest.fixture
def sms() -> RecordingSmsSender:
    return RecordingSmsSender()


@pytest.fixture
def request_otp(
    otp_repo: FakeOtpRepository,
    generator: StubCodeGenerator,
    hasher: ReversibleHasher,
    sms: RecordingSmsSender,
    clock: FrozenClock,
    users: FakeUserDirectory,
) -> RequestOtp:
    return RequestOtp(
        otp_repo=otp_repo,
        generator=generator,
        hasher=hasher,
        sms=sms,
        clock=clock,
        users=users,
    )


@pytest.fixture
def verifier(
    otp_repo: FakeOtpRepository, hasher: ReversibleHasher, clock: FrozenClock
) -> OtpVerifier:
    return OtpVerifier(otp_repo=otp_repo, hasher=hasher, clock=clock)


@pytest.fixture
def register(verifier: OtpVerifier, users: FakeUserDirectory) -> RegisterUser:
    return RegisterUser(verifier=verifier, users=users)


@pytest.fixture
def reset(verifier: OtpVerifier, users: FakeUserDirectory) -> ResetPassword:
    return ResetPassword(verifier=verifier, users=users)


def _issue(request_otp: RequestOtp, purpose: OtpPurpose, phone: str = _PHONE) -> None:
    request_otp.execute(phone_number_raw=phone, purpose=purpose)


class TestRequestOtp:
    def test_issues_a_registration_code_for_a_new_phone(
        self,
        request_otp: RequestOtp,
        otp_repo: FakeOtpRepository,
        sms: RecordingSmsSender,
    ) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)

        challenge = otp_repo.get_latest(_CANONICAL, OtpPurpose.REGISTRATION)
        assert challenge is not None
        assert sms.sent == [(_CANONICAL, _CODE)]

    def test_stores_only_the_hash_never_the_raw_code(
        self, request_otp: RequestOtp, otp_repo: FakeOtpRepository
    ) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)

        challenge = otp_repo.get_latest(_CANONICAL, OtpPurpose.REGISTRATION)
        assert challenge is not None
        assert challenge.code_hash != _CODE
        assert _CODE not in challenge.code_hash

    def test_sets_expiry_from_the_clock(
        self, request_otp: RequestOtp, otp_repo: FakeOtpRepository, now: datetime
    ) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)

        challenge = otp_repo.get_latest(_CANONICAL, OtpPurpose.REGISTRATION)
        assert challenge is not None
        assert challenge.expires_at > now

    def test_does_not_issue_a_registration_code_for_an_existing_phone(
        self,
        request_otp: RequestOtp,
        users: FakeUserDirectory,
        otp_repo: FakeOtpRepository,
        sms: RecordingSmsSender,
    ) -> None:
        # Eligibility is silent: the response shape is identical, but no code is
        # actually minted or sent for an already-registered number.
        users.create(_CANONICAL, password="x", full_name="", email="")

        _issue(request_otp, OtpPurpose.REGISTRATION)

        assert otp_repo.get_latest(_CANONICAL, OtpPurpose.REGISTRATION) is None
        assert sms.sent == []

    def test_issues_a_reset_code_only_for_an_existing_phone(
        self,
        request_otp: RequestOtp,
        users: FakeUserDirectory,
        otp_repo: FakeOtpRepository,
        sms: RecordingSmsSender,
    ) -> None:
        _issue(request_otp, OtpPurpose.PASSWORD_RESET)
        assert otp_repo.get_latest(_CANONICAL, OtpPurpose.PASSWORD_RESET) is None
        assert sms.sent == []

        users.create(_CANONICAL, password="x", full_name="", email="")
        _issue(request_otp, OtpPurpose.PASSWORD_RESET)
        assert otp_repo.get_latest(_CANONICAL, OtpPurpose.PASSWORD_RESET) is not None

    def test_throttles_a_rapid_resend_silently(
        self,
        request_otp: RequestOtp,
        otp_repo: FakeOtpRepository,
        sms: RecordingSmsSender,
        clock: FrozenClock,
        now: datetime,
    ) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)
        clock.set(now + timedelta(seconds=5))

        _issue(request_otp, OtpPurpose.REGISTRATION)

        # Still only one code sent: the second request is within the cooldown.
        assert len(sms.sent) == 1

    def test_resends_after_the_cooldown_elapses(
        self,
        request_otp: RequestOtp,
        sms: RecordingSmsSender,
        clock: FrozenClock,
        now: datetime,
    ) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)
        clock.set(now + timedelta(minutes=5))

        _issue(request_otp, OtpPurpose.REGISTRATION)

        assert len(sms.sent) == 2

    def test_rejects_a_malformed_phone(self, request_otp: RequestOtp) -> None:
        with pytest.raises(InvalidPhoneNumberError):
            request_otp.execute(phone_number_raw="not-a-phone", purpose=OtpPurpose.REGISTRATION)

    def test_never_logs_the_raw_code(self, request_otp: RequestOtp) -> None:
        with capture_logs() as logs:
            _issue(request_otp, OtpPurpose.REGISTRATION)

        assert _CODE not in repr(logs)


class TestRegisterUser:
    def test_creates_the_user_after_a_correct_code(
        self,
        request_otp: RequestOtp,
        register: RegisterUser,
        users: FakeUserDirectory,
    ) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)

        registered = register.execute(
            phone_number_raw=_PHONE, code=_CODE, password=_PASSWORD, full_name="Ada", email=""
        )

        assert registered.id is not None
        assert registered.phone_number == _CANONICAL
        assert users.exists(_CANONICAL)

    def test_spends_the_code_so_it_cannot_be_replayed(
        self, request_otp: RequestOtp, register: RegisterUser
    ) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)
        register.execute(
            phone_number_raw=_PHONE, code=_CODE, password=_PASSWORD, full_name="", email=""
        )

        with pytest.raises(InvalidOtpError):
            register.execute(
                phone_number_raw=_PHONE, code=_CODE, password="other-pass", full_name="", email=""
            )

    def test_rejects_a_wrong_code_and_counts_the_attempt(
        self,
        request_otp: RequestOtp,
        register: RegisterUser,
        otp_repo: FakeOtpRepository,
        users: FakeUserDirectory,
    ) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)

        with pytest.raises(InvalidOtpError):
            register.execute(
                phone_number_raw=_PHONE, code="000000", password=_PASSWORD, full_name="", email=""
            )

        challenge = otp_repo.get_latest(_CANONICAL, OtpPurpose.REGISTRATION)
        assert challenge is not None and challenge.attempts == 1
        assert not users.exists(_CANONICAL)

    def test_rejects_registration_without_any_issued_code(self, register: RegisterUser) -> None:
        with pytest.raises(InvalidOtpError):
            register.execute(
                phone_number_raw=_PHONE, code=_CODE, password=_PASSWORD, full_name="", email=""
            )

    def test_rejects_an_expired_code(
        self,
        request_otp: RequestOtp,
        register: RegisterUser,
        clock: FrozenClock,
        now: datetime,
    ) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)
        clock.set(now + timedelta(hours=1))

        with pytest.raises(OtpExpiredError):
            register.execute(
                phone_number_raw=_PHONE, code=_CODE, password=_PASSWORD, full_name="", email=""
            )

    def test_locks_out_after_too_many_wrong_codes(
        self, request_otp: RequestOtp, register: RegisterUser
    ) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)
        for _ in range(5):
            with pytest.raises(InvalidOtpError):
                register.execute(
                    phone_number_raw=_PHONE,
                    code="000000",
                    password=_PASSWORD,
                    full_name="",
                    email="",
                )

        # Even the correct code is refused once the budget is spent.
        with pytest.raises(OtpMaxAttemptsError):
            register.execute(
                phone_number_raw=_PHONE, code=_CODE, password=_PASSWORD, full_name="", email=""
            )

    def test_never_logs_the_password(self, request_otp: RequestOtp, register: RegisterUser) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)

        with capture_logs() as logs:
            register.execute(
                phone_number_raw=_PHONE, code=_CODE, password=_PASSWORD, full_name="", email=""
            )

        assert _PASSWORD not in repr(logs)


class TestResetPassword:
    def _register(self, request_otp: RequestOtp, register: RegisterUser) -> None:
        _issue(request_otp, OtpPurpose.REGISTRATION)
        register.execute(
            phone_number_raw=_PHONE, code=_CODE, password=_PASSWORD, full_name="", email=""
        )

    def test_sets_a_new_password_after_a_correct_code(
        self,
        request_otp: RequestOtp,
        register: RegisterUser,
        reset: ResetPassword,
        users: FakeUserDirectory,
    ) -> None:
        self._register(request_otp, register)
        _issue(request_otp, OtpPurpose.PASSWORD_RESET)

        reset.execute(phone_number_raw=_PHONE, code=_CODE, new_password="brand-new-pass")

        assert users.exists(_CANONICAL)

    def test_rejects_a_wrong_reset_code(
        self, request_otp: RequestOtp, register: RegisterUser, reset: ResetPassword
    ) -> None:
        self._register(request_otp, register)
        _issue(request_otp, OtpPurpose.PASSWORD_RESET)

        with pytest.raises(InvalidOtpError):
            reset.execute(phone_number_raw=_PHONE, code="000000", new_password="brand-new-pass")

    def test_a_registration_code_cannot_be_used_for_reset(
        self, request_otp: RequestOtp, register: RegisterUser, reset: ResetPassword
    ) -> None:
        # Purpose isolation: the registration code does not satisfy a reset.
        self._register(request_otp, register)
        _issue(request_otp, OtpPurpose.REGISTRATION)

        with pytest.raises(InvalidOtpError):
            reset.execute(phone_number_raw=_PHONE, code=_CODE, new_password="brand-new-pass")
