"""Domain exceptions for the tax context.

A single base (``TaxError``) lets a caller catch the whole family; the specific subclasses
carry the meaning a use case or transport needs. Pure Python -- no framework.
"""

from __future__ import annotations


class TaxError(Exception):
    """Base class for every tax-domain error."""


class InvalidMoneyError(TaxError):
    """Raised when a taxable amount is not a valid, representable, non-negative value."""


class InvalidTaxRateError(TaxError):
    """Raised when a tax rate is not a valid, non-negative percentage within bounds."""
