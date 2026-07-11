# ADR 0005 — Phone-first identity and cookie-delivered JWT auth

- Status: Accepted
- Date: 2026-06-28

## Context
Phase 1 requires a custom user model and authentication. The primary market is
Iran, where the mobile number is the natural account identifier (OTP-based
onboarding follows in the next slice). Tokens must be delivered in a way that is
resistant to theft from the browser.

Two forces shape this slice:

- **Django constraints.** The user must be an `AbstractBaseUser` and
  `AUTH_USER_MODEL` should be set before the first migration that references it,
  so the custom model is introduced now, not retrofitted.
- **Clean Architecture vs. pragmatism.** Token issuance/validation is framework
  machinery owned by SimpleJWT and `django.contrib.auth`. `CLAUDE.md` explicitly
  allows thin, framework-direct code where there is no real business rule, and
  reserves the full entity/use-case/repository ceremony for the core domain.

## Decision

### Identity model
- `domain/identity/` holds the one genuine business rule as a value object:
  `PhoneNumber` normalizes the many spellings an Iranian user might type
  (`09123456789`, `+989123456789`, `00989…`, spaced/dashed) into a single
  canonical E.164 form (`+989XXXXXXXXX`). It is pure Python and self-validating;
  malformed or non-Iranian numbers raise `InvalidPhoneNumberError`.
- `infrastructure/identity/` owns the custom `User(AbstractBaseUser,
  PermissionsMixin)` with `phone_number` as `USERNAME_FIELD` (unique), plus an
  optional `email`/`full_name`. Its `UserManager` runs every phone through the
  domain value object before persisting, so any spelling collapses to one stored
  identity and collides on the unique key.
- No separate domain `User` entity or repository is introduced: the user is
  inherently a Django concern, and duplicating it as a pure entity would be
  ceremony without payoff. This is the pragmatism clause in action.

### Authentication
- Tokens are delivered as **HttpOnly cookies**, not in the response body or the
  `Authorization` header, so client-side JavaScript cannot read them — removing
  the usual XSS token-theft vector. `CookieJWTAuthentication` reads the access
  token from the cookie and falls back to the header for non-browser API clients.
- Cookies are `HttpOnly`, `SameSite=Lax` (CSRF-resistant: a cross-site POST does
  not carry the cookie), and `Secure` whenever `DEBUG` is off.
- Endpoints under `auth/`: `login` (phone + password → sets access/refresh
  cookies), `refresh` (refresh cookie → new access cookie), `logout` (clears
  cookies), and `me` (returns the authenticated user). Views are thin: validate,
  normalize the phone via the domain rule, authenticate, move tokens into cookies.
- Auth failures return a **uniform 401** regardless of cause (unknown user, wrong
  password, malformed phone) so the endpoint does not leak whether an account
  exists.
- `login`/`refresh`/`logout` opt out of cookie authentication
  (`authentication_classes = []`): the browser auto-sends a possibly-expired
  access cookie, and validating it in the auth layer would wrongly reject these
  public endpoints with a 401.

### Audit & logging
- Auth events are logged structurally (`login_succeeded` with `user_id`,
  `login_failed`). The password is never logged, and the audit subject is the
  stable **user id**, never the phone number, which is PII. The channel slice's
  `_actor` helper was updated accordingly (id, not username/phone).

## Consequences
- The phone rule lives in one pure-Python place, reused by the model manager and
  the login view, and unit-tested without a database.
- Switching `AUTH_USER_MODEL` changed how tests construct users (phone, not
  `username`); the channel integration tests were updated in this slice.
- **Known limitations, deferred:**
  - Logout clears the browser cookies but does not blacklist the tokens; an
    already-captured access token stays valid until expiry (15 min) and a refresh
    token until 7 days. Token blacklisting (the SimpleJWT `token_blacklist` app)
    is a follow-up, tracked on the Phase 1 roadmap.
  - Registration, password reset, and mobile OTP are the **next** Phase 1 slice;
    this slice only establishes the model and the login/session mechanics.
  - Channel-scoped object permissions (django-guardian) still await the two-layer
    RBAC slice; writes remain staff-only for now (see ADR 0004).
