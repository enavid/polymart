"""Ports (interfaces) for the payment use cases.

The application layer depends only on these abstractions; concrete adapters (Django ORM,
the order-context bridge, the gateways, a real clock and reference generator, in-memory
fakes) live elsewhere and are injected at the composition root, keeping the dependency
rule pointing inward.

The central abstraction is ``PaymentGateway`` -- the port/adapter seam the whole phase is
built around. A method (COD today; online/card-to-card later) is a swappable adapter, not
a core dependency: the use case resolves one through ``PaymentGatewayRegistry`` and asks
it to ``start`` a payment, never knowing which concrete gateway answered. ``OrderReader``
is a narrow read boundary onto the order context: the payment context learns an order's
owner, currency, total, and status without depending on the order domain.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from src.domain.payment.entities import Payment
from src.domain.payment.exceptions import UnsupportedPaymentMethodError
from src.domain.payment.value_objects import Money, PaymentMethod, PaymentReference


@dataclass(frozen=True)
class PayableOrder:
    """An order flattened for the payment context (no order-domain types leak here).

    Only what the payment use case needs: the order is already resolved owner-scoped by
    the reader, so the owner is not re-carried here. ``total`` is the exact captured order
    total (a ``Decimal``, never a float); ``status`` is the order's lifecycle state as a
    plain string, which the use case checks against the states that still accept payment.
    """

    number: str
    currency: str
    total: Decimal
    status: str
    # The channel the order was placed in, so a per-channel setting (e.g. the card-to-card
    # destination card) can be resolved for it.
    channel: str


class OrderReader(ABC):
    """Narrow read boundary onto the order context, for the amount and payability check.

    Owner-scoped: an order that is not the caller's (or does not exist) resolves to
    ``None``, so payment can never reveal whether another shopper's order exists, and the
    amount is always the server's captured total -- never a client-supplied figure.
    """

    @abstractmethod
    def get_payable(self, owner: str, number: str) -> PayableOrder | None:
        """Return the owner's order (flattened), or ``None`` if it is not theirs/unknown."""


class NextActionType(StrEnum):
    """What the shopper must do next after a payment is initiated.

    * ``NONE`` -- nothing: an offline method (COD) is settled out of band, so the shopper
      is simply shown a confirmation.
    * ``REDIRECT`` -- send the shopper to an external gateway (online, a later slice).
    """

    NONE = "none"
    REDIRECT = "redirect"


@dataclass(frozen=True)
class PaymentIntent:
    """The immutable facts a gateway needs to start a payment.

    Assembled by the use case from the resolved order; the amount is the captured order
    total, so a gateway can never be asked to charge a client-chosen figure.
    """

    reference: PaymentReference
    order_number: str
    amount: Money
    method: PaymentMethod


@dataclass(frozen=True)
class PaymentStartResult:
    """What a gateway reports after starting a payment.

    ``next_action`` tells the caller what the shopper must do; ``redirect_url`` is set only
    when ``next_action`` is ``REDIRECT``. ``gateway_reference`` is the provider's own handle
    for the started payment (an online gateway's "authority"/token) which the callback later
    verifies against; it is ``None`` for an offline method (COD). The gateway does not mutate
    the payment's status here -- an offline method leaves it ``pending`` (collected out of
    band), and an online method leaves it ``pending`` until its callback confirms.
    """

    next_action: NextActionType
    redirect_url: str | None = None
    gateway_reference: str | None = None


@dataclass(frozen=True)
class PaymentVerification:
    """The outcome of verifying (capturing) an online payment with the gateway.

    Verification is the source of truth for whether money was actually collected -- the
    browser redirect that triggers it can be spoofed, so the server always re-confirms with
    the gateway. ``provider_reference`` is the gateway's definitive receipt id on success.
    """

    captured: bool
    provider_reference: str | None = None


class PaymentGateway(ABC):
    """A payment method's adapter: the port every gateway (COD, online, ...) implements.

    Declaring the seam here (and resolving a concrete one through the registry) is what
    lets a new method be added as an adapter without touching the domain or the use case.
    """

    @property
    @abstractmethod
    def method(self) -> PaymentMethod:
        """The payment method this gateway handles."""

    @abstractmethod
    def start(self, intent: PaymentIntent) -> PaymentStartResult:
        """Begin settling the intent and report what the shopper must do next."""


class OnlinePaymentGateway(PaymentGateway):
    """A redirect gateway that also *verifies* (captures) a payment after the callback.

    Split from the base ``PaymentGateway`` (ISP): an offline method like COD implements only
    ``start`` and never verifies, while an online gateway adds ``verify`` -- the server-side
    confirmation that actually captures the funds. The capture use case requires this
    capability, so a method whose gateway is not online cannot be captured.
    """

    @abstractmethod
    def verify(self, *, gateway_reference: str, amount: Money) -> PaymentVerification:
        """Confirm and capture the payment at the gateway, by its ``gateway_reference``.

        Idempotent at the provider: verifying an already-captured reference reports the same
        captured outcome rather than double-charging.
        """


class PaymentGatewayRegistry:
    """Resolves a payment method to its registered gateway (the pluggable seam).

    Framework-free so it can be the shared extension point: each gateway adapter is
    registered here at the composition root, and a method with no adapter raises
    ``UnsupportedPaymentMethodError`` rather than silently doing nothing.
    """

    def __init__(self, gateways: tuple[PaymentGateway, ...]) -> None:
        self._by_method: dict[PaymentMethod, PaymentGateway] = {}
        for gateway in gateways:
            # A duplicate registration is a wiring bug, not a runtime condition; fail loud.
            if gateway.method in self._by_method:
                raise ValueError(f"duplicate gateway for method {gateway.method.value!r}")
            self._by_method[gateway.method] = gateway

    def for_method(self, method: PaymentMethod) -> PaymentGateway:
        """Return the gateway for ``method``, or raise ``UnsupportedPaymentMethodError``."""
        try:
            return self._by_method[method]
        except KeyError:
            raise UnsupportedPaymentMethodError(method.value) from None


class PaymentRepository(ABC):
    """Persistence boundary for the Payment aggregate.

    Reads are always scoped to the owner, so one shopper can never resolve another's
    payment (there is no un-scoped ``get`` by reference).
    """

    @abstractmethod
    def add(self, payment: Payment) -> Payment:
        """Persist a new payment and return it with its assigned id."""

    @abstractmethod
    def get_for_owner(self, owner: str, reference: str) -> Payment:
        """Return the owner's payment by reference, or raise ``PaymentNotFoundError``."""

    @abstractmethod
    def get_for_order(self, owner: str, order_number: str) -> Payment:
        """Return the owner's payment for an order, or raise ``PaymentNotFoundError``.

        Returns the most recent payment for the order; used to show the payment on the
        order-detail page.
        """

    @abstractmethod
    def active_for_order(self, owner: str, order_number: str) -> Payment | None:
        """Return the order's still-open payment (the double-initiation guard), or ``None``.

        A spent payment (failed/cancelled/voided) does not count, so a shopper whose first
        attempt failed can start a fresh one.
        """

    @abstractmethod
    def find_by_gateway_reference(self, gateway_reference: str) -> Payment | None:
        """Return the payment with this gateway handle (a plain, unlocked read), or ``None``.

        Used by the callback view to resolve which order to redirect the shopper back to,
        independently of the (possibly async) capture. Not owner-scoped: the callback holds
        only the unguessable authority.
        """

    @abstractmethod
    def get_by_gateway_reference_for_update(self, gateway_reference: str) -> Payment | None:
        """Return the payment with this gateway handle under a row lock, or ``None``.

        Used by capture, which is *not* owner-scoped (a gateway callback carries no user
        session -- only the unguessable authority). The row lock serializes concurrent
        callbacks for the same reference so only one can capture; the second observes the
        already-captured status and no-ops (idempotency).
        """

    @abstractmethod
    def get_by_reference_for_update(self, reference: str) -> Payment | None:
        """Return the payment with this public reference under a row lock, or ``None``.

        Used by refund and the card-to-card staff confirm/reject, all *staff* actions
        addressed by the payment's public reference (not owner-scoped -- staff act on any
        shopper's payment, gated by the manage-orders permission at the transport). The row
        lock serializes concurrent settlements so only one transition wins; the second
        observes the new status and no-ops.
        """

    @abstractmethod
    def get_active_for_order_for_update(self, owner: str, order_number: str) -> Payment | None:
        """Return the owner's still-open payment for an order under a row lock, or ``None``.

        Used by the buyer submitting a card-to-card transfer reference -- an *owner-scoped*
        write, so another shopper's payment is never reachable. The lock serializes a
        concurrent submit against a staff confirm/reject on the same payment.
        """

    @abstractmethod
    def update_status(self, payment: Payment) -> Payment:
        """Persist a status change for an already-stored payment and return it."""

    @abstractmethod
    def update_transfer_reference(self, payment: Payment) -> Payment:
        """Persist the buyer's submitted card-to-card transfer reference and return it."""


class PaidOrders(ABC):
    """Narrow boundary onto the order context: mark an order paid when its payment captures.

    The payment context does not own orders; it only signals that money was collected. The
    adapter drives the order's own state machine (``pending -> paid``) so the order context
    stays authoritative over its lifecycle.
    """

    @abstractmethod
    def mark_paid(self, order_number: str) -> None:
        """Transition the order to ``paid``. A no-op if it is already paid (idempotent)."""


@dataclass(frozen=True)
class CardToCardDestination:
    """The merchant's receiving card a buyer transfers to for a card-to-card payment.

    Per-channel configuration (each channel/store may collect on its own card), resolved by
    the order's channel. Not a secret -- it is shown to the buyer so they can make the manual
    transfer -- but only exposed to the order's own owner.
    """

    card_number: str
    card_holder: str


class CardToCardDirectory(ABC):
    """Resolves a channel to its card-to-card receiving card (a per-channel setting)."""

    @abstractmethod
    def card_for(self, channel: str) -> CardToCardDestination | None:
        """Return the channel's destination card, or ``None`` if none is configured."""


class WalletCredit(ABC):
    """Narrow boundary onto the wallet context: credit a shopper's store-credit balance.

    The payment context does not own wallets; a refund only signals that value should be
    returned as internal credit. The adapter delegates to the wallet's own credit use case,
    running inside the refund's transaction (so the payment's refund and the wallet credit
    commit together) and idempotently by ``source_reference`` (a defensive second guard on
    top of the refund's own captured -> refunded idempotency).
    """

    @abstractmethod
    def credit(
        self,
        *,
        owner: str,
        amount: Decimal,
        currency: str,
        source_reference: str,
        reason: str,
        actor: str,
    ) -> None:
        """Credit ``amount`` (``Decimal``, never a float) to the owner's wallet."""


class WalletDebit(ABC):
    """Narrow boundary onto the wallet context: spend a shopper's store-credit balance.

    The payment context does not own wallets; pay-with-wallet only signals that the order
    total should be taken from internal credit. The adapter delegates to the wallet's own
    debit use case, running inside the payment's transaction (so the wallet debit and the
    payment's capture commit together) and idempotently by ``source_reference`` (a defensive
    second guard on top of the order's single-active-payment rule).

    A balance that cannot cover the amount is refused by raising the payment context's own
    ``InsufficientWalletBalanceError`` -- the adapter translates the wallet's insufficient-funds
    error, so no wallet-domain exception crosses this seam.
    """

    @abstractmethod
    def debit(
        self,
        *,
        owner: str,
        amount: Decimal,
        currency: str,
        source_reference: str,
        reason: str,
        actor: str,
    ) -> None:
        """Debit ``amount`` (``Decimal``, never a float) from the owner's wallet.

        Raises ``InsufficientWalletBalanceError`` if the balance cannot cover it.
        """


class PaymentReferenceGenerator(ABC):
    """Source of a fresh, unguessable payment reference, injected for deterministic tests."""

    @abstractmethod
    def next(self) -> PaymentReference:
        """Return a new payment reference."""


class Clock(ABC):
    """Source of the current time, injected so ``created_at`` is testable.

    The payment context owns its own ``Clock`` port (the dependency rule keeps contexts
    decoupled); the trivial system adapter lives in infrastructure.
    """

    @abstractmethod
    def now(self) -> datetime:
        """Return the current timezone-aware time."""


class UnitOfWork(ABC):
    """The transaction boundary for initiating a payment.

    ``atomic()`` returns a context manager; the payability re-check, the guard against a
    concurrent double-initiation, the gateway start, the persist, and the audit write all
    commit together or roll back together on any exception.
    """

    @abstractmethod
    def atomic(self) -> AbstractContextManager[None]:
        """Return a context manager that runs its body as one atomic transaction."""
