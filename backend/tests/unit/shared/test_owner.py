"""Unit tests for the shared owner-id redaction helper.

``safe_owner`` renders an owner id safe to write to logs and the audit trail: a user
id passes through unchanged, while a guest id -- whose token is a bearer session
credential -- is reduced to a short, non-reversible fingerprint.
"""

from __future__ import annotations

import hashlib

from src.application.shared.owner import safe_owner


class TestSafeOwner:
    def test_a_user_owner_passes_through_unchanged(self) -> None:
        # ``u:<pk>`` is a stable primary key, not a secret -- keep it as-is so a user
        # stays directly correlatable in logs and audit rows.
        assert safe_owner("u:42") == "u:42"

    def test_a_guest_owner_is_reduced_to_a_short_token_fingerprint(self) -> None:
        expected = hashlib.sha256(b"tok-secret").hexdigest()[:12]

        result = safe_owner("g:tok-secret")

        assert result == f"g:{expected}"

    def test_the_raw_guest_token_never_appears_in_the_result(self) -> None:
        # The whole point: the bearer credential must not survive into anything logged.
        assert "tok-secret" not in safe_owner("g:tok-secret")

    def test_the_guest_fingerprint_is_deterministic(self) -> None:
        # The same guest must correlate across events, so hashing is stable.
        assert safe_owner("g:tok-abc") == safe_owner("g:tok-abc")

    def test_different_guest_tokens_produce_different_fingerprints(self) -> None:
        assert safe_owner("g:tok-abc") != safe_owner("g:tok-xyz")

    def test_an_empty_guest_token_is_still_fingerprinted(self) -> None:
        expected = hashlib.sha256(b"").hexdigest()[:12]

        assert safe_owner("g:") == f"g:{expected}"

    def test_an_unrecognized_shape_passes_through_unchanged(self) -> None:
        # Defensive: an id that is neither ``u:`` nor ``g:`` is returned as-is rather
        # than assumed sensitive (nothing else mints owner ids).
        assert safe_owner("7") == "7"
