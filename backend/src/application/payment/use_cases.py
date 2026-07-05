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
    OrderReader,
    PaymentGatewayRegistry,
    PaymentIntent,
    PaymentReferenceGenerator,
    PaymentRepository,
    UnitOfWork,
)
from src.application.shared.owner import safe_owner
from src.domain.audit.entities import FieldChange
from src.domain.payment.entities import Payment
from src.domain.payment.exceptions import (
    InvalidPaymentMethodError,
    OrderNotPayableError,
    PaymentAlreadyExistsError,
    PaymentOrderNotFoundError,
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
