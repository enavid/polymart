"""Owner-id helpers shared across contexts that key aggregates by an opaque owner.

The cart and order contexts identify an aggregate's owner by an opaque, prefixed string
minted at the HTTP boundary (``src.interface.api.guest``): ``u:<pk>`` for an
authenticated user, ``g:<token>`` for a guest. The user form is a stable primary key --
safe to write anywhere. The guest form embeds the session *token*, which is a bearer
credential (possession of it grants access to that guest's cart and orders), so it must
never reach the structured logs or the durable audit trail verbatim.

``safe_owner`` renders an owner id safe to observe: a user id passes through, while a
guest id is reduced to a short, non-reversible fingerprint of its token. Guests stay
correlatable across log lines and audit rows without the raw credential ever being
written; the raw token continues to live only in the ownership column that must match
it (``cart.guest_token`` / ``order.guest_token``).
"""

from __future__ import annotations

import hashlib

_GUEST_PREFIX = "g:"
_FINGERPRINT_LENGTH = 12


def safe_owner(owner: str) -> str:
    """Return an owner id safe to log/audit: users pass through, guests are hashed.

    A ``g:<token>`` owner becomes ``g:<sha256(token)[:12]>`` -- deterministic (so the
    same guest correlates across events) but non-reversible (the bearer token cannot be
    recovered from it). Any other shape (a ``u:<pk>`` user, or an unexpected value) is
    returned unchanged, since only the guest token is sensitive.
    """
    if not owner.startswith(_GUEST_PREFIX):
        return owner
    token = owner[len(_GUEST_PREFIX) :]
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:_FINGERPRINT_LENGTH]
    return f"{_GUEST_PREFIX}{digest}"
