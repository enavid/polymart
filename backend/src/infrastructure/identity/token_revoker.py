"""SimpleJWT implementation of the TokenRevoker port.

Blacklists every outstanding refresh token for a user. Access tokens are
short-lived and not individually tracked; revoking the refresh tokens stops new
access tokens from being minted, which is the durable half of a logout/reset.
"""

from __future__ import annotations

from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from src.application.identity.ports import TokenRevoker


class SimpleJwtTokenRevoker(TokenRevoker):
    """Revoke a user's refresh tokens via SimpleJWT's blacklist tables."""

    def revoke_all(self, user_id: int) -> None:
        for token in OutstandingToken.objects.filter(user_id=user_id):
            # get_or_create keeps this idempotent: revoking twice is harmless.
            BlacklistedToken.objects.get_or_create(token=token)
