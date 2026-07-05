"""Celery tasks for the payment context.

The online callback hands settlement off to a background task so the shopper's return is
fast and the capture is retryable if it fails transiently -- and, crucially, idempotent, so
a retry (or a duplicate callback) never double-captures or double-pays the order. Discovered
by Celery's ``autodiscover_tasks``. In tests Celery runs eagerly, so the capture completes
synchronously and the result is observable immediately.

The task builds the use case through the payment composition root (the same wiring the
views use), keeping a single place that knows how the adapters are assembled.
"""

from __future__ import annotations

import structlog
from celery import shared_task

from src.application.payment.use_cases import CapturePaymentCommand
from src.domain.payment.exceptions import PaymentError
from src.interface.api.payment.container import build_capture_payment

logger = structlog.get_logger(__name__)


@shared_task(name="payment.capture_online_payment")
def capture_online_payment(gateway_reference: str, *, succeeded: bool) -> str | None:
    """Settle an online payment from its callback (idempotent). Returns the final status.

    A missing/invalid reference is logged and swallowed rather than retried forever -- a
    callback for a payment that no longer resolves is not something a retry can fix. Any
    other unexpected error (e.g. the order was cancelled between initiation and this
    callback, so it can no longer be marked paid -- the whole capture rolls back) is logged
    at error level and swallowed too, so one bad message never crashes the worker; such a
    case leaves the payment un-captured for reconciliation rather than silently paying a
    cancelled order.
    """
    try:
        payment = build_capture_payment().execute(
            CapturePaymentCommand(gateway_reference=gateway_reference, succeeded=succeeded)
        )
    except PaymentError as exc:
        logger.warning("payment_capture_task_failed", error=type(exc).__name__)
        return None
    except Exception as exc:
        # A background task must not crash the worker on a single bad message.
        logger.error("payment_capture_task_error", error=type(exc).__name__)
        return None
    return payment.status.value
