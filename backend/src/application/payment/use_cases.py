"""Payment use cases (interactors).

Each use case orchestrates the domain to fulfil one application intent: pure
orchestration, dependencies via constructor injection, business rules in the domain,
side effects (logging, audit) observable.

Initiating a payment re-checks the order's payability, guards against a concurrent
double-initiation, asks the resolved gateway to start it, persists the aggregate, and
writes the money-relevant audit entry -- all inside one ``UnitOfWork.atomic()``. The
amount is always the order's captured total (never a client-supplied figure), and the
structured logs deliberately never carry the amount or any PII: the actor is the stable,
redacted owner id, and the amount lives only on the audit entry.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.application.audit.ports import AuditRecorder
from src.application.payment.ports import (
    Clock,
    NextActionType,
    OnlinePaymentGateway,
    OrderReader,
    PaidOrders,
    PaymentGatewayRegistry,
    PaymentIntent,
    PaymentReferenceGenerator,
    PaymentRepository,
    PaymentVerification,
    UnitOfWork,
    WalletCredit,
    WalletDebit,
)
from src.application.shared.owner import safe_owner
from src.domain.audit.entities import FieldChange
from src.domain.payment.entities import Payment
from src.domain.payment.exceptions import (
    GatewayCannotCaptureError,
    InvalidPaymentMethodError,
    OrderNotPayableError,
    PaymentAlreadyExistsError,
    PaymentNotFoundError,
    PaymentNotRefundableError,
    PaymentOrderNotFoundError,
    WalletOwnerRequiredError,
    WalletPaymentRequiresUserError,
)
from src.domain.payment.value_objects import (
    Money,
    OrderRef,
    PaymentMethod,
    PaymentReference,
    PaymentStatus,
)

logger = structlog.get_logger(__name__)

# Only a placed-but-unpaid order accepts a payment; a paid/cancelled/fulfilled order does
# not. The order context owns this vocabulary; the payment context couples to it only
# through this one narrow string (mirroring the status carried on ``PayableOrder``).
_PAYABLE_ORDER_STATUS = "pending"

_RESOURCE_PAYMENT = "payment"
_ACTION_PAYMENT_INITIATED = "payment.initiated"
_ACTION_PAYMENT_CAPTURED = "payment.captured"
_ACTION_PAYMENT_FAILED = "payment.failed"
_ACTION_PAYMENT_REFUNDED = "payment.refunded"

# The reason recorded on the wallet credit a refund produces, and the owner prefix a wallet
# requires (a wallet always belongs to a registered user, never a guest).
_REFUND_REASON = "refund"
_USER_OWNER_PREFIX = "u:"
# The reason recorded on the wallet debit a pay-with-wallet produces.
_WALLET_PAYMENT_REASON = "order_payment"

# The statuses from which a callback can still settle a payment; anything else is already
# resolved and the callback is a no-op (idempotency).
_SETTLEABLE_STATUSES = frozenset({PaymentStatus.PENDING, PaymentStatus.AUTHORIZED})


@dataclass(frozen=True)
class InitiatePaymentCommand:
    """Input for starting a payment against one of the shopper's own orders.

    ``owner`` is the resolved cart/order owner id (``u:<pk>`` / ``g:<token>``); ``method``
    is the raw string chosen at checkout, parsed into a ``PaymentMethod`` here.
    """

    owner: str
    order_number: str
    method: str


@dataclass(frozen=True)
class PaymentResult:
    """The outcome of initiating a payment: the persisted payment plus what to do next."""

    payment: Payment
    next_action: NextActionType
    redirect_url: str | None = None


class InitiatePayment:
    """Start a payment for the owner's order, atomically.

    The order is resolved owner-scoped (so another shopper's order is indistinguishable
    from a nonexistent one) and must be payable (still pending, no active payment). The
    amount is captured from the order total, the resolved gateway starts the payment, the
    aggregate is persisted ``pending``, and the initiation is audited -- all in one
    transaction, so any failure leaves no payment and no trail behind.
    """

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        orders: OrderReader,
        payments: PaymentRepository,
        gateways: PaymentGatewayRegistry,
        references: PaymentReferenceGenerator,
        clock: Clock,
        audit: AuditRecorder,
    ) -> None:
        self._uow = unit_of_work
        self._orders = orders
        self._payments = payments
        self._gateways = gateways
        self._references = references
        self._clock = clock
        self._audit = audit

    def execute(self, command: InitiatePaymentCommand) -> PaymentResult:
        method = self._parse_method(command.method)
        # Resolve the gateway before opening the transaction: an unsupported method is a
        # request error, not something to roll a transaction back over.
        gateway = self._gateways.for_method(method)

        with self._uow.atomic():
            order = self._orders.get_payable(command.owner, command.order_number)
            if order is None:
                raise PaymentOrderNotFoundError(command.order_number)
            if order.status != _PAYABLE_ORDER_STATUS:
                raise OrderNotPayableError(order.number, order.status)
            if self._payments.active_for_order(command.owner, order.number) is not None:
                raise PaymentAlreadyExistsError(order.number)

            amount = Money(amount=order.total, currency=order.currency)
            payment = Payment(
                reference=self._references.next(),
                order_ref=OrderRef(order.number),
                owner=command.owner,
                method=method,
                amount=amount,
                status=PaymentStatus.PENDING,
                created_at=self._clock.now(),
            )
            result = gateway.start(
                PaymentIntent(
                    reference=payment.reference,
                    order_number=order.number,
                    amount=amount,
                    method=method,
                )
            )
            # An online gateway hands back its own handle (an "authority"); record it so the
            # callback can verify this exact payment. COD returns none, leaving it unset.
            if result.gateway_reference is not None:
                payment = payment.with_gateway_reference(result.gateway_reference)
            saved = self._payments.add(payment)
            self._audit.record(
                action=_ACTION_PAYMENT_INITIATED,
                resource_type=_RESOURCE_PAYMENT,
                resource_id=saved.reference.value,
                actor=safe_owner(command.owner),
                changes=(
                    FieldChange(field="status", after=PaymentStatus.PENDING.value),
                    FieldChange(field="method", after=method.value),
                    FieldChange(field="amount", after=str(amount.amount)),
                    FieldChange(field="order", after=order.number),
                ),
            )

        # Logged outside the money detail: reference, order, method, and next action --
        # never the amount. The owner is redacted so a guest's session token never reaches
        # the logs (see safe_owner).
        logger.info(
            "payment_initiated",
            owner=safe_owner(command.owner),
            payment_reference=saved.reference.value,
            order_number=order.number,
            method=method.value,
            next_action=result.next_action.value,
            currency=order.currency,
        )
        return PaymentResult(
            payment=saved,
            next_action=result.next_action,
            redirect_url=result.redirect_url,
        )

    @staticmethod
    def _parse_method(raw: str) -> PaymentMethod:
        try:
            return PaymentMethod(raw)
        except ValueError as exc:
            raise InvalidPaymentMethodError(f"unknown payment method: {raw!r}") from exc


@dataclass(frozen=True)
class PayWithWalletCommand:
    """Input for settling one of the shopper's own orders from their wallet balance.

    ``owner`` is the resolved order owner id; pay-with-wallet requires a registered user
    (``u:<pk>``) -- a guest has no wallet. There is no amount here: it is always the order's
    captured total, taken from the order itself, never a client-supplied figure.
    """

    owner: str
    order_number: str


class PayWithWallet:
    """Pay for the owner's order from their wallet balance, atomically and instantly.

    Unlike a gateway method, wallet payment settles synchronously: the order is resolved
    owner-scoped and must be payable (still pending, no active payment), the amount is
    captured from the order total, the wallet is debited for the full amount (refused if the
    balance cannot cover it), the payment is created and immediately captured, and the order
    is marked paid -- all in one transaction, so an uncovered balance or any failure leaves no
    payment, no debit, and an unpaid order behind. A guest is refused up front (no wallet).
    """

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        orders: OrderReader,
        payments: PaymentRepository,
        wallet_debit: WalletDebit,
        paid_orders: PaidOrders,
        references: PaymentReferenceGenerator,
        clock: Clock,
        audit: AuditRecorder,
    ) -> None:
        self._uow = unit_of_work
        self._orders = orders
        self._payments = payments
        self._wallet_debit = wallet_debit
        self._paid_orders = paid_orders
        self._references = references
        self._clock = clock
        self._audit = audit

    def execute(self, command: PayWithWalletCommand) -> PaymentResult:
        # A wallet always belongs to a registered user; refuse a guest before opening the
        # transaction (a request error, not something to roll a transaction back over).
        if not command.owner.startswith(_USER_OWNER_PREFIX):
            raise WalletPaymentRequiresUserError()

        with self._uow.atomic():
            order = self._orders.get_payable(command.owner, command.order_number)
            if order is None:
                raise PaymentOrderNotFoundError(command.order_number)
            if order.status != _PAYABLE_ORDER_STATUS:
                raise OrderNotPayableError(order.number, order.status)
            if self._payments.active_for_order(command.owner, order.number) is not None:
                raise PaymentAlreadyExistsError(order.number)

            amount = Money(amount=order.total, currency=order.currency)
            payment = Payment(
                reference=self._references.next(),
                order_ref=OrderRef(order.number),
                owner=command.owner,
                method=PaymentMethod.WALLET,
                amount=amount,
                status=PaymentStatus.PENDING,
                created_at=self._clock.now(),
            )
            saved = self._payments.add(payment)
            self._audit_initiated(saved, amount=amount, order_number=order.number)

            # Move the money internally: debit the wallet for the full total (refused, and the
            # whole transaction rolled back, if the balance cannot cover it), then capture the
            # payment and mark the order paid -- all together.
            self._wallet_debit.debit(
                owner=command.owner,
                amount=amount.amount,
                currency=amount.currency,
                source_reference=saved.reference.value,
                reason=_WALLET_PAYMENT_REASON,
                actor=safe_owner(command.owner),
            )
            captured = self._payments.update_status(saved.capture())
            self._paid_orders.mark_paid(order.number)
            self._audit_captured(captured, amount=amount, order_number=order.number)

        logger.info(
            "payment_paid_with_wallet",
            owner=safe_owner(command.owner),
            payment_reference=captured.reference.value,
            order_number=order.number,
            currency=amount.currency,
        )
        return PaymentResult(payment=captured, next_action=NextActionType.NONE)

    def _audit_initiated(self, payment: Payment, *, amount: Money, order_number: str) -> None:
        self._audit.record(
            action=_ACTION_PAYMENT_INITIATED,
            resource_type=_RESOURCE_PAYMENT,
            resource_id=payment.reference.value,
            actor=safe_owner(payment.owner),
            changes=(
                FieldChange(field="status", after=PaymentStatus.PENDING.value),
                FieldChange(field="method", after=PaymentMethod.WALLET.value),
                FieldChange(field="amount", after=str(amount.amount)),
                FieldChange(field="order", after=order_number),
            ),
        )

    def _audit_captured(self, payment: Payment, *, amount: Money, order_number: str) -> None:
        self._audit.record(
            action=_ACTION_PAYMENT_CAPTURED,
            resource_type=_RESOURCE_PAYMENT,
            resource_id=payment.reference.value,
            actor=safe_owner(payment.owner),
            changes=(
                FieldChange(
                    field="status",
                    before=PaymentStatus.PENDING.value,
                    after=PaymentStatus.CAPTURED.value,
                ),
                FieldChange(field="amount", after=str(amount.amount)),
                FieldChange(field="order", after=order_number),
                FieldChange(field="paid_with", after="wallet"),
            ),
        )


class GetMyPayment:
    """Read one of the authenticated shopper's own payments by reference (never another's)."""

    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    def execute(self, *, owner: str, reference: str) -> Payment:
        # Validate the shape first; a malformed reference can never match, and surfacing it
        # as "not found" (rather than a distinct error) avoids leaking structure.
        canonical = PaymentReference(reference).value
        return self._payments.get_for_owner(owner, canonical)


class GetPaymentForOrder:
    """Read the payment for one of the authenticated shopper's own orders."""

    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    def execute(self, *, owner: str, order_number: str) -> Payment:
        canonical = OrderRef(order_number).value
        return self._payments.get_for_order(owner, canonical)


class GetPaymentByGatewayReference:
    """Resolve a payment from a gateway callback's authority (not owner-scoped).

    The callback holds only the unguessable gateway reference, no user session; this read
    lets the callback learn which order to redirect the shopper back to. It reveals nothing
    a holder of the authority is not already entitled to.
    """

    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    def execute(self, *, gateway_reference: str) -> Payment:
        payment = self._payments.find_by_gateway_reference(gateway_reference)
        if payment is None:
            raise PaymentNotFoundError(gateway_reference)
        return payment


@dataclass(frozen=True)
class CapturePaymentCommand:
    """Input for settling an online payment from its gateway callback.

    ``gateway_reference`` is the provider's authority (from the redirect/webhook), the only
    handle a callback carries -- there is no user session, so capture is *not* owner-scoped;
    the unguessable authority plus the server-side ``verify`` are the authority. ``succeeded``
    is the callback's own status hint (the shopper completed vs cancelled at the gateway); a
    cancel fails the payment without a verify, while a success is always re-confirmed with the
    gateway (the redirect is never trusted on its own).
    """

    gateway_reference: str
    succeeded: bool


class CapturePayment:
    """Settle an online payment from its callback, idempotently and atomically.

    Locks the payment by its gateway reference (so two concurrent callbacks serialize), and:
    an already-settled payment is returned unchanged (idempotency -- a repeated callback never
    double-captures or double-pays the order); a cancelled callback fails a still-open payment;
    a successful callback re-verifies with the gateway (the source of truth) and, on capture,
    moves the payment to ``captured``, marks the order ``paid``, and audits ``payment.captured``
    -- all in one transaction, so a failure anywhere leaves the payment and order untouched.
    """

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        payments: PaymentRepository,
        gateways: PaymentGatewayRegistry,
        paid_orders: PaidOrders,
        audit: AuditRecorder,
    ) -> None:
        self._uow = unit_of_work
        self._payments = payments
        self._gateways = gateways
        self._paid_orders = paid_orders
        self._audit = audit

    def execute(self, command: CapturePaymentCommand) -> Payment:
        with self._uow.atomic():
            payment = self._payments.get_by_gateway_reference_for_update(command.gateway_reference)
            if payment is None:
                raise PaymentNotFoundError(command.gateway_reference)

            # Idempotency: a payment already settled (captured or spent) is returned as-is; a
            # duplicate callback must never re-capture or re-pay the order.
            if payment.status not in _SETTLEABLE_STATUSES:
                logger.info(
                    "payment_callback_ignored",
                    owner=safe_owner(payment.owner),
                    payment_reference=payment.reference.value,
                    status=payment.status.value,
                )
                return payment

            if not command.succeeded:
                return self._settle_failed(payment, reason="cancelled_at_gateway")

            verification = self._verify(payment)
            if not verification.captured:
                return self._settle_failed(payment, reason="verification_failed")
            return self._settle_captured(
                payment, provider_reference=verification.provider_reference
            )

    def _verify(self, payment: Payment) -> PaymentVerification:
        gateway = self._gateways.for_method(payment.method)
        # Capture needs a verifiable (online) gateway with a recorded authority; a payment
        # lacking either cannot be settled via the callback path (a wiring/logic error).
        if not isinstance(gateway, OnlinePaymentGateway) or payment.gateway_reference is None:
            raise GatewayCannotCaptureError(payment.method.value)
        return gateway.verify(gateway_reference=payment.gateway_reference, amount=payment.amount)

    def _settle_captured(self, payment: Payment, *, provider_reference: str | None) -> Payment:
        captured = self._payments.update_status(payment.capture())
        # Money actually moved: mark the order paid in the same transaction.
        self._paid_orders.mark_paid(payment.order_ref.value)
        self._audit.record(
            action=_ACTION_PAYMENT_CAPTURED,
            resource_type=_RESOURCE_PAYMENT,
            resource_id=payment.reference.value,
            actor=safe_owner(payment.owner),
            changes=(
                FieldChange(
                    field="status",
                    before=PaymentStatus.PENDING.value,
                    after=PaymentStatus.CAPTURED.value,
                ),
                FieldChange(field="amount", after=str(payment.amount.amount)),
                FieldChange(field="order", after=payment.order_ref.value),
                FieldChange(field="provider_reference", after=provider_reference),
            ),
        )
        logger.info(
            "payment_captured",
            owner=safe_owner(payment.owner),
            payment_reference=payment.reference.value,
            order_number=payment.order_ref.value,
            currency=payment.amount.currency,
        )
        return captured

    def _settle_failed(self, payment: Payment, *, reason: str) -> Payment:
        failed = self._payments.update_status(payment.fail())
        self._audit.record(
            action=_ACTION_PAYMENT_FAILED,
            resource_type=_RESOURCE_PAYMENT,
            resource_id=payment.reference.value,
            actor=safe_owner(payment.owner),
            changes=(
                FieldChange(
                    field="status",
                    before=payment.status.value,
                    after=PaymentStatus.FAILED.value,
                ),
                FieldChange(field="reason", after=reason),
            ),
        )
        logger.info(
            "payment_failed",
            owner=safe_owner(payment.owner),
            payment_reference=payment.reference.value,
            order_number=payment.order_ref.value,
            reason=reason,
        )
        return failed


@dataclass(frozen=True)
class RefundPaymentCommand:
    """Input for refunding a captured payment to the shopper's wallet (a staff action).

    ``reference`` is the payment's public handle (from the staff URL); ``actor`` is the
    resolved staff id performing the refund (``u:<pk>``), recorded on the audit trail. There
    is no amount here -- a refund always returns the full captured amount, taken from the
    payment itself, never a client-supplied figure.
    """

    reference: str
    actor: str


class RefundPayment:
    """Refund a captured payment to the shopper's wallet, idempotently and atomically.

    Locks the payment by its reference (so two concurrent refunds serialize), and: an
    already-refunded payment is returned unchanged (idempotency -- a repeat never
    double-credits the wallet); a payment that is not captured is refused; a guest payment
    has no wallet to receive the credit and is refused. Otherwise the payment moves to
    ``refunded``, the shopper's wallet is credited with the full amount, and the refund is
    audited -- all in one transaction, so any failure leaves the payment and wallet untouched.
    """

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        payments: PaymentRepository,
        wallet_credit: WalletCredit,
        audit: AuditRecorder,
    ) -> None:
        self._uow = unit_of_work
        self._payments = payments
        self._wallet_credit = wallet_credit
        self._audit = audit

    def execute(self, command: RefundPaymentCommand) -> Payment:
        # Validate the reference shape up front; a malformed one can never match a payment
        # (surfaced as "not found" at the transport, never a distinct error).
        canonical = PaymentReference(command.reference).value
        with self._uow.atomic():
            payment = self._payments.get_by_reference_for_update(canonical)
            if payment is None:
                raise PaymentNotFoundError(canonical)

            # Idempotency: an already-refunded payment is returned as-is; a repeat must never
            # credit the wallet twice (the wallet's own source-reference guard backs this up).
            if payment.status == PaymentStatus.REFUNDED:
                logger.info(
                    "payment_refund_ignored",
                    owner=safe_owner(payment.owner),
                    payment_reference=payment.reference.value,
                    status=payment.status.value,
                )
                return payment

            if payment.status != PaymentStatus.CAPTURED:
                raise PaymentNotRefundableError(payment.reference.value, payment.status.value)
            if not payment.owner.startswith(_USER_OWNER_PREFIX):
                raise WalletOwnerRequiredError(payment.reference.value)

            refunded = self._payments.update_status(payment.refund())
            self._wallet_credit.credit(
                owner=payment.owner,
                amount=payment.amount.amount,
                currency=payment.amount.currency,
                source_reference=payment.reference.value,
                reason=_REFUND_REASON,
                actor=command.actor,
            )
            self._audit.record(
                action=_ACTION_PAYMENT_REFUNDED,
                resource_type=_RESOURCE_PAYMENT,
                resource_id=payment.reference.value,
                actor=command.actor,
                changes=(
                    FieldChange(
                        field="status",
                        before=PaymentStatus.CAPTURED.value,
                        after=PaymentStatus.REFUNDED.value,
                    ),
                    FieldChange(field="amount", after=str(payment.amount.amount)),
                    FieldChange(field="order", after=payment.order_ref.value),
                    FieldChange(field="refunded_to", after="wallet"),
                ),
            )

        logger.info(
            "payment_refunded",
            owner=safe_owner(payment.owner),
            payment_reference=payment.reference.value,
            order_number=payment.order_ref.value,
            currency=payment.amount.currency,
            actor=command.actor,
        )
        return refunded
