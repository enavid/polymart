"""Domain exceptions for the address context.

A single base (``AddressError``) lets the transport layer catch the whole family and
map it to a sensible default, while the specific subclasses carry the meaning a view
needs to choose a precise status code.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations


class AddressError(Exception):
    """Base class for every address-domain error."""


class InvalidRecipientNameError(AddressError):
    """Raised when a recipient name is blank or too long."""


class InvalidPhoneNumberError(AddressError):
    """Raised when a recipient phone number is not a valid Iranian mobile number."""


class InvalidProvinceError(AddressError):
    """Raised when a province is blank or too long."""


class InvalidCityError(AddressError):
    """Raised when a city is blank or too long."""


class InvalidPostalCodeError(AddressError):
    """Raised when a postal code is not exactly ten digits."""


class InvalidAddressLineError(AddressError):
    """Raised when an address line is blank or too long."""


class InvalidAddressIdError(AddressError):
    """Raised when an address id is structurally malformed."""


class AddressNotFoundError(AddressError):
    """Raised when no address matches the owner/id pair."""

    def __init__(self, address_id: str) -> None:
        super().__init__(f"address not found: {address_id}")
        self.address_id = address_id


class AddressLimitExceededError(AddressError):
    """Raised when an owner already has the maximum number of saved addresses."""

    def __init__(self, owner: str, limit: int) -> None:
        super().__init__(f"address limit exceeded for owner {owner}: max {limit}")
        self.owner = owner
        self.limit = limit
