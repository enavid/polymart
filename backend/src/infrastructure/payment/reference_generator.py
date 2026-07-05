"""Payment-reference generator adapter.

Produces an opaque, unguessable public payment handle. Using cryptographic randomness
(not a database sequence) means a payment reference in a URL reveals nothing about how
many payments exist and cannot be walked to reach another shopper's payment. Uniqueness
is additionally guaranteed by the ``reference`` unique constraint; a collision at this
width is astronomically unlikely. A deliberate twin of the order-number generator.
"""

from __future__ import annotations

import secrets

from src.application.payment.ports import PaymentReferenceGenerator
from src.domain.payment.value_objects import PaymentReference

# Crockford-style alphabet: upper-case, no ambiguous 0/O/1/I/L, so a reference is easy to
# read aloud. 12 characters over this 30-symbol alphabet is ~59 bits of entropy.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
_REFERENCE_LENGTH = 12
_PREFIX = "PAY-"


class SecurePaymentReferenceGenerator(PaymentReferenceGenerator):
    """Generate ``PAY-XXXXXXXXXXXX`` from cryptographically secure randomness."""

    def next(self) -> PaymentReference:
        body = "".join(secrets.choice(_ALPHABET) for _ in range(_REFERENCE_LENGTH))
        return PaymentReference(f"{_PREFIX}{body}")
