"""Order-number generator adapter.

Produces an opaque, unguessable public order reference. Using cryptographic randomness
(not a database sequence) means an order number in a URL reveals nothing about how many
orders exist and cannot be walked to reach another shopper's order. Uniqueness is
additionally guaranteed by the ``number`` unique constraint; a collision at this width
is astronomically unlikely.
"""

from __future__ import annotations

import secrets

from src.application.order.ports import OrderNumberGenerator
from src.domain.order.value_objects import OrderNumber

# Crockford-style alphabet: upper-case, no ambiguous 0/O/1/I/L, so a number is easy to
# read aloud. 12 characters over this 30-symbol alphabet is ~59 bits of entropy.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
_NUMBER_LENGTH = 12
_PREFIX = "ORD-"


class SecureOrderNumberGenerator(OrderNumberGenerator):
    """Generate ``ORD-XXXXXXXXXXXX`` from cryptographically secure randomness."""

    def next(self) -> OrderNumber:
        body = "".join(secrets.choice(_ALPHABET) for _ in range(_NUMBER_LENGTH))
        return OrderNumber(f"{_PREFIX}{body}")
