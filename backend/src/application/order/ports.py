"""Ports (interfaces) for the order use cases.

The application layer depends only on these abstractions; concrete adapters (Django
ORM, catalog/channel/cart bridges, a real clock and number generator, in-memory fakes)
live elsewhere and are injected at the composition root, keeping the dependency rule
pointing inward.

Several ports are *narrow* boundaries onto neighbouring bounded contexts: the order
context learns a variant's current price, a channel's currency, and a cart's contents,
and deducts/returns inventory, without depending on the catalog, channel, or cart
domains.

The ``UnitOfWork`` is the transaction boundary. Checkout must be all-or-nothing across
several aggregates (deduct stock, create the order, clear the cart, write the audit
entry); running the whole use case inside ``uow.atomic()`` makes a failure anywhere --
an oversell, say -- roll every step back, so stock is never deducted without an order
and the audit entry never records a purchase that did not commit.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.domain.order.entities import Order
from src.domain.order.value_objects import Money, OrderNumber, OrderStatus


@dataclass(frozen=True)
class CheckoutLine:
    """One line of a cart, flattened for checkout (no cart-domain types leak here)."""

    sku: str
    quantity: int


@dataclass(frozen=True)
class OrderPage:
    """One page of a shopper's orders plus the full count (for pagination)."""

    items: tuple[Order, ...]
    total: int


class OrderRepository(ABC):
    """Persistence boundary for the Order aggregate.

    Reads are always scoped to the owner, so one shopper can never resolve another's
    order (there is no un-scoped ``get`` by number).
    """

    @abstractmethod
    def add(self, order: Order) -> Order:
        """Persist a new order (with its lines) and return it with its assigned id."""

    @abstractmethod
    def get(self, number: str) -> Order:
        """Return any order by number (not owner-scoped), or raise ``OrderNotFoundError``.

        Used only behind the ``manage_orders`` permission (issuing a pre-invoice for any
        order); every shopper-facing read goes through the owner-scoped methods below.
        """

    @abstractmethod
    def get_for_owner(self, owner: str, number: str) -> Order:
        """Return the owner's order by number, or raise ``OrderNotFoundError``."""

    @abstractmethod
    def get_for_update(self, owner: str, number: str) -> Order:
        """Return the owner's order under a row lock (for a status change).

        Locking serializes concurrent mutations of the same order so, e.g., two
        cancels cannot both read a ``pending`` order and both restock.
        """

    @abstractmethod
    def get_for_update_any(self, number: str) -> Order:
        """Return any order by number under a row lock (not owner-scoped).

        The staff-fulfilment counterpart of ``get_for_update``: used only behind the
        ``manage_orders`` permission (shipping/pickup transitions on any order), so it locks
        the row without owner scoping. Raises ``OrderNotFoundError`` if none exists.
        """

    @abstractmethod
    def list_for_owner(
        self, owner: str, *, limit: int, offset: int
    ) -> tuple[tuple[Order, ...], int]:
        """Return one page of the owner's orders (newest first) plus the total count."""

    @abstractmethod
    def set_status(self, order: Order, status: OrderStatus) -> Order:
        """Persist a status change for an already-stored order and return it."""


class CartForCheckout(ABC):
    """Narrow boundary onto the cart context: read its contents and clear it."""

    @abstractmethod
    def line_items(self, owner: str, channel: str) -> tuple[CheckoutLine, ...]:
        """Return the owner's cart lines for the channel (empty tuple if none)."""

    @abstractmethod
    def clear(self, owner: str, channel: str) -> None:
        """Empty the owner's cart for the channel (a no-op if already empty)."""


class PricingReader(ABC):
    """Narrow read boundary onto the catalog for capturing an order line's price."""

    @abstractmethod
    def price_of(self, sku: str, channel: str) -> Money | None:
        """Return the variant's current unit price in the channel, or ``None``."""


class VariantWeightReader(ABC):
    """Narrow read boundary onto the catalog for a variant's shipping weight (grams).

    Used to compute an order's total weight for weight-based shipping rates; an unknown SKU
    (or one with no weight set) weighs 0, so a fully-unweighed catalog behaves exactly as the
    flat-rate case (weight never affects the quote).
    """

    @abstractmethod
    def weight_of(self, skus: Sequence[str]) -> dict[str, int]:
        """Return the per-sku weight in grams, batched (missing/unset skus omitted or 0)."""


class ChannelReader(ABC):
    """Narrow read boundary onto the channel context for the order currency."""

    @abstractmethod
    def currency_of(self, channel: str) -> str | None:
        """Return the channel's ISO 4217 currency code, or ``None`` if it does not exist."""


@dataclass(frozen=True)
class ShippingQuote:
    """A quoted shipping method for a channel, flattened for checkout capture.

    Carries the stable ``method_code``, its display ``name``, and its ``cost`` -- everything
    the order context needs to capture the selection onto the order, with no shipping-domain
    type leaking across the boundary.
    """

    method_code: str
    method_name: str
    cost: Money
    is_pickup: bool = False


class ShippingRateReader(ABC):
    """Narrow boundary onto the shipping context: quote a chosen method for checkout.

    The order context asks "what does this method cost in this channel?" and captures the
    answer; whether the rate comes from config or a table (and how zones are matched later)
    is invisible here.
    """

    @abstractmethod
    def quote(
        self,
        *,
        channel: str,
        method_code: str,
        currency: str,
        province: str,
        city: str,
        weight_grams: int = 0,
    ) -> ShippingQuote | None:
        """Quote the method for the channel, destination, and order weight, or ``None``.

        The ``province``/``city`` are the captured shipping destination; the rate is resolved
        for the zone the province falls into (falling back to the method's default rate). The
        ``weight_grams`` is the order's total shipping weight, used by a weight-priced method to
        pick the applicable bracket (ignored by a flat/zoned method). The ``currency`` is the
        resolved order currency; an adapter returns ``None`` (rather than a mismatched quote) if
        a configured method's currency does not match it.
        """


@dataclass(frozen=True)
class TaxQuote:
    """The tax computed for a taxable amount, flattened for checkout capture.

    Carries the applied ``rate`` (a percentage, for display on the order) and the computed
    ``amount`` -- everything the order context needs to capture tax onto the order, with no
    tax-domain type leaking across the boundary.
    """

    rate: Decimal
    amount: Money


class TaxCalculator(ABC):
    """Narrow boundary onto the tax context: compute the tax due at checkout.

    The order context asks "what tax is due on this taxable amount in this channel?" and
    captures the answer; whether the rate comes from config or a table (and how classes/zones
    are matched later) is invisible here. The tax *amount* is computed by the tax context (with
    its rounding rule), never recomputed by the order context.
    """

    @abstractmethod
    def calculate(self, *, channel: str, taxable: Money) -> TaxQuote | None:
        """Return the tax due on ``taxable`` in the channel, or ``None`` if the channel is untaxed.

        The ``taxable`` amount is the base the tax applies to (goods subtotal plus shipping) in
        the resolved order currency. ``None`` means the channel levies no tax, so the order
        captures no tax line and its total is the pre-tax amount.
        """


@dataclass(frozen=True)
class OwnedAddress:
    """A shopper's saved address, flattened for checkout (no address-domain types leak here)."""

    recipient_name: str
    phone_number: str
    province: str
    city: str
    postal_code: str
    line1: str
    line2: str | None


@dataclass(frozen=True)
class InlineShippingAddress:
    """A one-off shipping address captured inline at checkout (a guest has no address book).

    Same shape as ``OwnedAddress`` but carries no id/owner: it is entered on the
    checkout form and captured onto the order directly, rather than resolved from a
    saved book entry. Transport (the serializer) validates its format; the order's
    ``ShippingAddress`` value object re-checks presence/length when it is built.
    """

    recipient_name: str
    phone_number: str
    province: str
    city: str
    postal_code: str
    line1: str
    line2: str | None


class AddressReader(ABC):
    """Narrow read boundary onto the address context for capturing a checkout's shipping address."""

    @abstractmethod
    def get_for_owner(self, owner: str, address_id: str) -> OwnedAddress | None:
        """Return the owner's saved address, or ``None`` if it does not exist or isn't theirs."""


class Inventory(ABC):
    """Boundary for moving on-hand stock as orders are placed and cancelled.

    ``deduct`` captures stock for a placed order and refuses an oversell; ``restock``
    returns it when an order is cancelled. Both take a row lock so concurrent moves on
    the same variant serialize instead of racing (the anti-overselling guarantee).
    """

    @abstractmethod
    def deduct(self, sku: str, quantity: int) -> None:
        """Withdraw ``quantity`` from the variant, or raise on an unknown SKU / oversell."""

    @abstractmethod
    def restock(self, sku: str, quantity: int) -> None:
        """Return ``quantity`` to the variant (the reverse of ``deduct``)."""


class OrderNumberGenerator(ABC):
    """Source of a fresh, unguessable order number, injected so it is deterministic in tests."""

    @abstractmethod
    def next(self) -> OrderNumber:
        """Return a new order number."""


class Clock(ABC):
    """Source of the current time, injected so ``placed_at`` is testable.

    The order context owns its own ``Clock`` port (the dependency rule keeps contexts
    decoupled); the trivial system adapter lives in infrastructure.
    """

    @abstractmethod
    def now(self) -> datetime:
        """Return the current timezone-aware time."""


class UnitOfWork(ABC):
    """The transaction boundary for a multi-aggregate use case.

    ``atomic()`` returns a context manager; everything performed inside it commits
    together or rolls back together on any exception.
    """

    @abstractmethod
    def atomic(self) -> AbstractContextManager[None]:
        """Return a context manager that runs its body as one atomic transaction."""
