# ADR 0006 — OTP-based registration and password reset

- Status: Accepted
- Date: 2026-06-28

## Context
Phase 1 calls for registration, login, and recovery with mobile OTP — the native
onboarding pattern in Iran. Password login already exists (ADR 0005). This slice
adds the one-time-code primitive and the two flows that consume it: creating an
account and resetting a forgotten password. A one-time code is genuinely
security-critical: it must expire, tolerate only a few wrong guesses, be usable
exactly once, and be scoped to a single flow.

## Decision

### Where the logic lives (Clean Architecture + pragmatism)
- **Domain (`domain/identity/`)** owns the genuine rules as pure Python:
  `OtpChallenge` (expiry, attempt budget, single-use) and the `OtpPurpose` enum.
  The challenge stores only the code's **hash**, never the code.
- **Application (`application/identity/`)** owns the policy via use cases —
  `RequestOtp`, `RegisterUser`, `ResetPassword` — and a shared `OtpVerifier`.
  Side effects are behind ports: `OtpRepository`, `CodeGenerator`, `CodeHasher`,
  `SmsSender`, `Clock`, `UserDirectory`. Nothing here imports a framework.
- **Infrastructure** provides the adapters: Django ORM repository (+ a
  `OtpChallengeModel` and migration), `SecretsCodeGenerator`, `HmacCodeHasher`,
  `LoggingSmsSender`, `SystemClock`, `DjangoUserDirectory`.
- **Interface** stays thin: `auth/otp/request`, `auth/register`,
  `auth/password-reset` parse input, call a use case, and map domain errors to
  HTTP. They issue no tokens of their own.

### Flow shape
- **Single-step verification.** The code is verified and spent in the same
  request that creates the account / sets the password. There is no standalone
  "verify" endpoint and no dangling "verified but unused" state to steal.
- **No auto-login on register.** Registration returns `201` with the user
  projection; the client then logs in (ADR 0005). This keeps the use case
  returning a pure DTO and keeps token glue out of the registration view.

### Security properties
- **Anti-enumeration.** `RequestOtp` is uniform: it always returns `202` with a
  generic message. A code is minted only when the phone is *eligible*
  (registration → no account yet; reset → an account exists); otherwise the
  request is silently skipped. The response cannot reveal which numbers have
  accounts. A malformed phone is the one non-uniform case (`400`), as it leaks
  only format, not existence.
- **Brute-force resistance.** Codes are 6 digits from `secrets`, valid for
  2 minutes, with a 5-attempt lockout. A wrong guess is counted and persisted
  *before* the failure is returned, so the lockout survives the failed request.
- **Replay/purpose isolation.** A verified code is consumed (single use) and is
  scoped to its `OtpPurpose`, so a registration code cannot reset a password.
- **Hashing.** Codes are stored as keyed HMAC-SHA256 (keyed by `SECRET_KEY`), so
  a leaked row cannot be brute-forced offline without also stealing the key;
  comparison is constant-time.
- **Resend cooldown.** A 60-second cooldown throttles SMS abuse; like
  eligibility, it is applied silently to preserve uniformity.
- **No secrets in logs.** The raw code, the password, and the full phone number
  never reach the logs — even in debug. The SMS adapter logs a masked phone and
  never the code; audit events carry the stable `user_id` and the `purpose`.

## Consequences
- New domain rules are unit-tested against fakes (no DB/clock/randomness);
  adapters and the full HTTP flows are integration-tested. Coverage stays at
  100%.
- The `SmsSender` port is the seam where a real Iranian gateway (Kavenegar,
  Ghasedak, …) plugs in; until then `LoggingSmsSender` records dispatch without
  the code.

## Known limitations / deferred
- **Concurrent attempt counter.** The wrong-guess counter is a read-modify-write
  locked only on write (`select_for_update`), mirroring the channel slice's
  documented pattern. Highly concurrent verification could under-count guesses.
  The robust fix is an atomic increment within a transaction that spans the
  read — i.e., the Unit-of-Work introduced in Phase 3. Real-world exploitability
  is low (6-digit code, 2-minute TTL, write serialization).
- **Token revocation on reset.** A password reset does not revoke already-issued
  access tokens (valid ≤ 15 min); this shares the token-blacklist follow-up
  already noted in ADR 0005.
- **Timing.** The eligible path does more work than the skipped path, a
  theoretical timing side-channel; constant-time uniformity is out of scope here.
