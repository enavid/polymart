# ADR 0031 — Address book

- Status: Accepted
- Date: 2026-07-02

## Context
ADR 0030 delivered checkout → order placement, leaving one remaining backend bullet in
Phase 3: "خرید مهمان، آدرس‌بوک، سفارش دستی/پیش‌فاکتور" (guest checkout, address book,
manual order/pre-invoice). Of the three, the address book is the self-contained slice —
it does not require the anonymous/session-identity modelling guest checkout needs (the
order/cart contexts currently model `owner` as an authenticated user's stable id, with
no guest concept at all), and it is a genuine prerequisite for the multi-step checkout
UI the roadmap still lists as outstanding. Guest checkout and manual/pre-invoice orders
remain open Phase 3 items, deliberately deferred to their own slices.

## Decision

### A new `address` bounded context, Clean-Architecture all the way down
- **Domain** (`domain/address`): its own value objects (`RecipientName`, `PhoneNumber`
  — Iranian mobile, duplicated from identity's per the established convention of never
  importing a neighbouring context's domain types; `Province`, `City`, `PostalCode` —
  ten Iranian digits; `AddressLine`; `AddressId` — opaque, mirroring `OrderNumber`) and
  the `Address` aggregate. `Address.with_details(...)` is the only way to edit contact
  details — it deliberately cannot touch `id`, `owner`, `is_default`, or `created_at`,
  so an edit can never accidentally reassign identity, ownership, or default status.
- **Application** (`application/address`): the ports and five use cases (`AddAddress`,
  `ListMyAddresses`, `UpdateAddress`, `DeleteAddress`, `SetDefaultAddress`).
- **Infrastructure** (`infrastructure/address`): the ORM model, mapper, repository, a
  CSPRNG id generator, and a clock.
- **Interface** (`interface/api/address`): thin DRF views over `addresses/`.

### Addresses are Iran-only, like the rest of the platform
There is no country field. `PhoneNumber` and `PostalCode` are both Iran-specific
formats, matching CLAUDE.md's framing of Iran as the first-class market; multi-country
support is a future concern, not something to design for speculatively here.

### Exactly one default per owner, enforced twice
The first address an owner saves always becomes their default — an address book with
addresses but no default would leave a future checkout with nothing to preselect.
Swapping the default (`SetDefaultAddress`, or `AddAddress` with `is_default=True`) is
atomic: the repository takes a row lock on the swap target and unsets any other default
for the owner in the same transaction. As defense in depth, the database also carries a
**partial unique constraint** — `UniqueConstraint(fields=["owner"], condition=Q(is_default=True))`
— so a bug in the application-level swap could never silently leave two defaults; it
would surface as an `IntegrityError` instead. This is deliberately *not* held to the
same atomicity rigor CLAUDE.md mandates for money/inventory paths (no owner-row locking
against a concurrent first-add race) — an address book carries no money or inventory
risk, and the failure mode of the one unhandled edge case (two concurrent "first
address" submissions from a brand-new owner) is a rare, low-severity, self-healing
oddity, not a correctness hazard.

### A defensive per-owner cap
`AddAddress` refuses a 21st address (`AddressLimitExceededError` → `409`) via a
`_MAX_ADDRESSES_PER_OWNER = 20` constant. This is not a business requirement — it is
the same defensive-cap posture already used elsewhere in the codebase (CSV import size,
order-history page size) against unbounded per-owner growth.

### Owner-scoping and opaque ids make IDOR structurally impossible
There is no owner id in any request body, and the address `id` is an opaque,
unguessable reference (`ADDR-` + 12 CSPRNG characters), mirroring `OrderNumber`. Every
repository read/write is scoped to the authenticated owner; a malformed id and a
not-found-or-not-yours id both surface as the same `404`, never a distinguishable `400`,
so the shape of a valid id is never probed. Verified in integration tests (owner-scoped
update/delete/set-default) and in the browser E2E (a second account never sees the
shopper's saved addresses).

### HTTP surface (all behind `IsAuthenticated`)
- `GET /addresses/` — the caller's own address book (default first).
- `POST /addresses/` — save a new address; `201`; `409` at the per-owner cap; `400` for
  invalid fields.
- `PUT /addresses/<id>/` — edit an existing address's contact/location details (never
  its default status); `404` if not found/not owned.
- `DELETE /addresses/<id>/` — remove an address; `204`.
- `POST /addresses/<id>/default/` — make an address the caller's sole default.

There is deliberately no `GET /addresses/<id>/`: the list already returns full address
objects, and the address-book UI edits directly from the list, so a separate detail
endpoint would be unused surface.

### Storefront UI
An `/addresses` page (linked from the header nav): a list of saved addresses (default
badge first), an inline add/edit form (shared between both flows), set-default, and
delete via an **inline confirmation** (no native browser dialog), matching the order
detail page's cancel-confirmation pattern. Backend field-level error detail is
technical/English and not shopper-appropriate (several address value objects raise with
just the raw invalid value, matching the existing `Sku`/`ChannelRef` convention), so the
UI shows a localized message instead — the same substitution `CartView` already makes
for checkout errors.

## Consequences
- **Positive.** Shoppers can maintain a small, curated set of shipping addresses ahead
  of the multi-step checkout UI that will consume them. Coverage is effectively 100% on
  the new domain/use-case code (excluding unused `__str__` conveniences, matching the
  order context's own precedent); default-exclusivity, the per-owner cap, and
  owner-scoped IDOR immunity are covered by integration tests against a real Postgres
  database and by a rigorous browser E2E suite (CRUD, boundary/invalid input, the exact
  cap boundary, and cross-account isolation).
- **Negative / deferred.** Guest checkout and manual/pre-invoice orders remain open
  Phase 3 items. The multi-step checkout UI does not yet read from the address book —
  wiring "select/edit an address at checkout" is the next slice. No audit action is
  emitted for a *failed* add/update (only successful mutations are recorded, matching
  every other context in this codebase).
- **Migration.** `address/0001_initial` adds `address_address`, including the partial
  unique constraint on `(owner, is_default=True)`.
- **PII.** Structured logs carry the address id and default flag but never the
  recipient's name, phone number, or physical address; those live only on the audit
  entry (before/after `city` only, not the full address) and the address row itself. The
  actor is the stable user id.
