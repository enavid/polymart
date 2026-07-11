"""Domain services for the tax context (pure Python, no framework).

Computing a tax amount from a taxable base and a rate is money arithmetic that belongs to
no single value object, so it lives here as a domain service -- defined and unit-tested in
the domain rather than buried in an adapter. This is the first place in the codebase where
money is *multiplied by a fraction* rather than by an integer, so it is also the first place
rounding is unavoidable: the result is quantized to the stored money precision with an
explicit, half-up rule (never a binary ``float``), so the computed tax is deterministic and
always representable as a captured amount.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from src.domain.tax.value_objects import Money, TaxRate

# Tax is quantized to the stored money precision (4 decimal places) so the amount can always
# be captured onto an order losslessly. ROUND_HALF_UP is stated explicitly rather than left
# to the ambient context, so the rounding of a money value is never accidental.
_TAX_QUANTUM = Decimal("0.0001")


def calculate_tax(taxable: Money, rate: TaxRate) -> Money:
    """Return the tax due on ``taxable`` at ``rate`` (exact ``Decimal``, half-up rounding).

    The multiplication is exact; only the final quantization rounds, and it does so half-up
    to the stored money precision. A zero rate yields zero tax in the taxable currency.
    """
    exact = taxable.amount * rate.fraction
    rounded = exact.quantize(_TAX_QUANTUM, rounding=ROUND_HALF_UP)
    return Money(amount=rounded, currency=taxable.currency)
