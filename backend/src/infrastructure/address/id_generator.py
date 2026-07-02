"""Address-id generator adapter.

Produces an opaque, unguessable public address reference. Using cryptographic
randomness (not a database sequence) means an address id in a URL reveals nothing
about how many addresses exist and cannot be walked to reach another shopper's
address. Uniqueness is additionally guaranteed by the ``address_id`` unique
constraint; a collision at this width is astronomically unlikely. A deliberate twin
of the order context's ``SecureOrderNumberGenerator``.
"""

from __future__ import annotations

import secrets

from src.application.address.ports import AddressIdGenerator
from src.domain.address.value_objects import AddressId

# Crockford-style alphabet: upper-case, no ambiguous 0/O/1/I/L, so an id is easy to
# read aloud. 12 characters over this 30-symbol alphabet is ~59 bits of entropy.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
_ID_LENGTH = 12
_PREFIX = "ADDR-"


class SecureAddressIdGenerator(AddressIdGenerator):
    """Generate ``ADDR-XXXXXXXXXXXX`` from cryptographically secure randomness."""

    def next(self) -> AddressId:
        body = "".join(secrets.choice(_ALPHABET) for _ in range(_ID_LENGTH))
        return AddressId(f"{_PREFIX}{body}")
