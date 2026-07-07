"""The per-channel card-to-card destination directory, backed by Django settings.

The merchant's receiving card is configuration, not shopper data, and it is sensitive
banking detail -- so it lives with the other payment-gateway settings (like the Zarinpal
merchant id and callback URLs) rather than in a public model or API. It is keyed by channel
slug (``PAYMENT_CARD_TO_CARD = {"<slug>": {"number": ..., "holder": ...}}``), so each channel
collects on its own card, resolved by the order's channel.
"""

from __future__ import annotations

from django.conf import settings

from src.application.payment.ports import CardToCardDestination, CardToCardDirectory

_NUMBER_KEY = "number"
_HOLDER_KEY = "holder"


class SettingsCardToCardDirectory(CardToCardDirectory):
    """Resolves a channel to its destination card from the ``PAYMENT_CARD_TO_CARD`` setting."""

    def card_for(self, channel: str) -> CardToCardDestination | None:
        configured = settings.PAYMENT_CARD_TO_CARD.get(channel)
        if not configured:
            return None
        number = configured.get(_NUMBER_KEY)
        holder = configured.get(_HOLDER_KEY)
        # A partial/misconfigured entry is treated as "not configured" rather than shown blank.
        if not number or not holder:
            return None
        return CardToCardDestination(card_number=number, card_holder=holder)
