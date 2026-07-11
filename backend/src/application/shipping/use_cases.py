"""Shipping use cases (interactors).

Two thin reads over the ``ShippingMethodReader`` port: list a channel's offered methods
(for the storefront to render at checkout), and resolve one chosen method (so checkout can
quote its price). Dependencies arrive by constructor injection; the source of the methods
is invisible here.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.application.shipping.ports import ShippingMethodReader
from src.domain.shipping.entities import ShippingMethod
from src.domain.shipping.exceptions import ShippingMethodNotFoundError
from src.domain.shipping.value_objects import Destination

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ListShippingMethodsQuery:
    """Input for listing a channel's offered shipping methods.

    ``destination`` (optional) selects the zoned rate for each method; without it, the
    default rates are listed.
    """

    channel: str
    destination: Destination | None = None


class ListShippingMethods:
    """List the shipping methods a channel offers (for rendering the checkout chooser)."""

    def __init__(self, reader: ShippingMethodReader) -> None:
        self._reader = reader

    def execute(self, query: ListShippingMethodsQuery) -> tuple[ShippingMethod, ...]:
        methods = self._reader.available_for(query.channel, query.destination)
        logger.debug("shipping_methods_listed", channel=query.channel, count=len(methods))
        return methods


class GetShippingMethod:
    """Resolve one offered method by code, or raise ``ShippingMethodNotFoundError``.

    Used by the order context's bridge adapter to quote the chosen method at checkout; the
    ``destination`` selects the zoned rate captured onto the order.
    """

    def __init__(self, reader: ShippingMethodReader) -> None:
        self._reader = reader

    def execute(
        self, *, channel: str, code: str, destination: Destination | None = None
    ) -> ShippingMethod:
        method = self._reader.get(channel, code, destination)
        if method is None:
            raise ShippingMethodNotFoundError(channel, code)
        return method
