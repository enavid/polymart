# ADR 0010 — Token revocation (logout blacklist + password-reset invalidation)

- Status: Accepted
- Date: 2026-06-28

## Context
The cookie-JWT auth slice (ADR 0005) and the OTP reset slice (ADR 0006) each left
one explicit follow-up: tokens issued before a logout or a password reset could
still be used until their natural expiry. A stateless JWT is valid until it
expires, so "log me out" and "reset my password" did not actually end existing
sessions — the refresh token kept minting fresh access tokens. This closes both
follow-ups for Phase 1.

## Decision
Enable SimpleJWT's `token_blacklist` app, which tracks issued refresh tokens
(`OutstandingToken`) and records revoked ones (`BlacklistedToken`). With it
installed, `RefreshToken.verify()` rejects a blacklisted token, so revoking the
refresh token stops new access tokens from being minted — the durable half of
ending a session. (Access tokens stay short-lived and untracked.)

- **Logout** blacklists the refresh token carried in the cookie. It stays
  best-effort: a missing or already-invalid token must not fail logout, and the
  cookies are cleared regardless.
- **Password reset** revokes *all* of the account's outstanding tokens. This is
  application policy ("a reset ends every existing session"), so it is expressed
  as a new `TokenRevoker` port injected into `ResetPassword` — the use case stays
  pure and unit-testable against a fake; the SimpleJWT adapter
  (`SimpleJwtTokenRevoker`) lives in infrastructure. Revocation runs only after
  the code is verified and the new password is set; a rejected reset revokes
  nothing.

## Consequences
- **Positive.** Logout and password reset now actually terminate sessions.
  `ResetPassword` depends on an abstraction (`TokenRevoker`), not on SimpleJWT, so
  the dependency rule holds and the revocation policy is tested without a DB.
- **Negative / deferred.** Revocation only bites refresh tokens; an access token
  already in hand stays valid until its short lifetime (15 min) elapses —
  acceptable, and the standard trade-off for stateless JWTs. The `token_blacklist`
  tables grow with issued tokens; pruning expired rows (SimpleJWT's
  `flushexpiredtokens`) is an operational task for later.
- **Migration.** Adds the third-party `token_blacklist` app's tables; no
  first-party migration.

## Notes
- The remaining identity follow-up — an **atomic OTP attempt counter** — is *not*
  addressed here: it needs use-case-controlled transactions (the Phase 3 Unit of
  Work), so it stays deferred to Phase 3 with the other transactional concerns.
