# ADR 0045 — Shipping zones (per-province zoned rates)

- Status: Accepted
- Date: 2026-07-11

## Context
ADR 0044 introduced flat-rate shipping: each channel offers a set of named methods, each
with one fixed price, quoted at checkout and captured onto the order. Real delivery pricing
depends on *where* the parcel goes — shipping to the capital costs less than a remote
province. This slice adds **shipping zones**: a method's price is resolved for the zone the
destination's province falls into, falling back to the method's default rate elsewhere.

It is the next-smallest coherent increment on the ADR 0044 seam. It deliberately does **not**
add weight/table rates, city-level matching, a zone admin panel, or per-zone delivery
windows — those remain later Phase 5 slices. The goal is to make the rate *destination-aware*
through the existing port/adapter, without the order context learning anything new about how
rates are computed.

## Decision

### Zones and zoned rates in the shipping domain
The `shipping` context gains three pure-Python domain concepts:

- **`ShippingZone`** entity — a stable `ShippingZoneCode`, a display `name`, and a non-empty
  set of `provinces`. `covers(province)` matches case- and whitespace-insensitively (so
  `"  Tehran "` and `"tehran"` are the same place). A zone that covers nothing is rejected.
- **`Destination`** value object — the `province` (required) and `city` (captured for a later,
  finer slice) an order ships to; `match_key` folds the province for tolerant matching.
- **`ZonedRate`** value object — a method's `default` price plus optional per-zone overrides
  (`by_zone`: zone code → `Money`). `for_zone(zone_code)` returns the override when present,
  else the default — the money-selection rule, kept in the domain so it is unit-tested rather
  than buried in an adapter. Every override must settle in the default's currency (a mixed
  table is a config bug, rejected at construction).

A domain service **`resolve_zone(province, zones)`** picks the first zone that covers a
province (zones are expected disjoint; first-match keeps the result deterministic if they
overlap). `ShippingMethod` is unchanged: it still carries a single resolved `price` — it now
represents *a method priced for a destination*, not a method priced flatly.

### Config-backed, behind the same reader port
Zones are configuration in this slice, like the flat rates: a new per-channel `SHIPPING_ZONES`
setting (keyed by slug), and each `SHIPPING_METHODS` entry may carry an optional `zone_rates`
map (zone code → price). The `ShippingMethodReader` port gains an optional `destination`:
`available_for(channel, destination)` and `get(channel, code, destination)`. The
`SettingsShippingMethodReader` resolves the destination's zone, then builds each method's
`ZonedRate` and projects the zone-resolved price. A malformed zone entry is skipped (logged),
never fatal — exactly as a malformed method is. Without a destination (or for a province in no
zone), the default rates are returned, so ADR 0044's behaviour is the zero-zone special case.

A later slice can move rates and zones to admin-managed models behind this same port without
the order context or the domain noticing — the seam ADR 0044 built is exactly what carries the
zoning.

### Checkout re-resolves the rate from the captured address
The order context's `ShippingRateReader.quote` gains `province`/`city` (the order context's own
strings — no shipping-domain type crosses the boundary). `PlaceOrder` already resolves the
shipping address before quoting; it now passes that address's province/city into the quote, so
the captured cost is **re-resolved server-side from the order's own address** rather than
trusting whatever price the client was shown. The `ConfiguredShippingRateReader` bridge builds
a shipping `Destination` and delegates to `GetShippingMethod`; an unknown or currency-mismatched
method still quotes `None` (→ 400/refused). Nothing else about capture changes: the cost is
still a `CapturedShipping` on the order and part of the relaxed `total == Σ lines + shipping.cost`
invariant. Manual/pre-invoice orders still carry no shipping.

### Storefront
`GET /shipping/methods/` accepts optional `province`/`city`; a malformed province degrades to
the default rates (a listing read should not 400, and the authoritative rate is re-resolved at
checkout anyway). The checkout chooser fetches methods for the selected address's province and
is keyed by the destination, so **changing the address refetches** and re-prices. Every money
value on screen is still the server's; the one place the UI combines two server amounts (the
preview total) still uses exact scaled-integer arithmetic.

## Consequences
- Shipping cost now varies by destination while the order, capture, invariant, audit, and
  event all stay exactly as ADR 0044 left them — the change is contained to how a method's
  price is *resolved*, proving the port/adapter seam holds.
- **Config**: dev/test/E2E define a discounted `tehran` zone (`standard` 30,000 vs the 50,000
  default; `express` 90,000 vs 120,000). The seeded shopper's address is in `تهران` (zoned
  rate); the guest checkout enters `"Tehran"` (latin) — a different string — so it falls back
  to the default rate. Matching is exact-normalized in this slice; province aliasing/canonical
  names are deferred.
- **Testing**: unit tests cover `ShippingZone.covers`, `Destination`, `ZonedRate.for_zone`
  (including the mixed-currency rejection), `resolve_zone`, and `PlaceOrder` quoting against the
  captured destination; integration tests cover the settings reader's zone resolution, the
  `/shipping/methods/` zoned query (and the overlong-province degrade-to-default), and the
  order→shipping bridge selecting the zoned rate; a frontend component test asserts the chooser
  requests the address province and shows the zoned price; a dedicated `shipping-zones` E2E
  proves, against the real stack, that a Tehran destination is quoted the zoned rate, that
  changing the address re-quotes, and that the placed order captures the server-re-resolved rate.
- **Deferred (later Phase 5 slices)**: weight/table rates; city-level zone matching and province
  aliasing; a zone/rate admin panel; per-zone delivery windows; and staff choosing a shipping
  method on a manual order.
