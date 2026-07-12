# ADR 0051 — Weight/table shipping rates + city-level matching + province aliasing (Phase 5, shipping slice)

- Status: Accepted
- Date: 2026-07-12

## Context
Flat + zoned shipping rates (ADR 0044/0045) price a method by destination province only.
Phase 5 asks for **weight/table rates**, **city-level zone matching**, and **province
aliasing**, plus a zone admin panel. Two scope decisions frame this slice:

1. **Weight comes from a real per-variant field.** Weight-based rates need an order weight;
   variants had no weight, so a structured `weight_grams` field is added to the catalog
   variant (not a free-typed dynamic attribute).
2. **Zones/methods stay in settings config** for now; a DB-backed zone/method model with a
   CRUD admin panel is deferred to its own later slice (it is a distinct architectural move —
   new persistence, RBAC, and UI — that deserves dedicated care).

## Decision
- **Per-variant weight.** `ProductVariant` gains `weight_grams` (a non-negative bounded int,
  0 = unset), persisted on `ProductVariantModel` (`catalog/0017`), round-tripped by the
  mapper, settable via the create-variant API + admin form, and shown on the variant detail.
- **Weight-table rates.** New `WeightBracket` (`up_to_grams` inclusive bound or `None`
  overflow, + price) and `WeightTable` (ordered brackets, single trailing overflow, strictly
  increasing bounds, one currency) value objects; `WeightTable.price_for(weight)` picks the
  first covering bracket. A `ShippingMethod` gains an optional `weight_table`: when set the
  method is weight-priced — `price` is the indicative "from" price (the lightest bracket) for
  browsing, and `method.quote(weight_grams)` resolves the actual cost. A method is priced
  *either* by a flat/zoned rate *or* by a weight table; configuring both on one method is a
  bug (skipped + logged). Config: a method entry carries `weight_brackets`.
- **Order weight at checkout.** The order context gains a narrow `VariantWeightReader` port
  (bridged to the catalog by `DjangoVariantWeightReader`); `PlaceOrder` computes the order's
  total weight (Σ variant weight × qty) and passes it to the shipping quote, which is now
  resolved **inside the transaction** (once the cart is read) because a weight-priced method
  needs the cart to price. An unweighed catalog contributes 0, so weight never affects a
  flat/zoned quote — the flat-rate case is unchanged. The captured cost is re-resolved
  server-side, never trusted from the client.
- **City-level matching.** `ShippingZone` gains an optional `cities` set; `covers` now takes a
  `Destination` and, when `cities` is non-empty, requires the province **and** the city to
  match (an empty `cities` covers the whole province). `resolve_zone` takes a `Destination`,
  so a fine city zone ordered before a broad province zone lets specific rates layer over
  general ones. Config: a zone entry may carry `cities`.
- **Province aliasing.** `SHIPPING_PROVINCE_ALIASES[channel]` maps an input province (any
  casing) to the canonical province a zone is configured under; the settings reader
  canonicalises the destination's province before matching, so a Latin "Tehran" resolves to
  the same zone as "تهران". An unknown province is left unchanged.

## Consequences
- Shipping can now price by weight brackets and match zones down to the city, with
  alias-tolerant province matching — all still behind the same `ShippingMethodReader` port,
  so the deferred DB-backed admin panel can replace the settings source without the order or
  domain layers noticing.
- The shipping quote moved inside the checkout transaction (it needs the cart weight); an
  unknown method now rolls the transaction back rather than being rejected before it, with
  the same observable outcome (nothing committed, no stock reserved — the quote is the first
  step).
- Dev/E2E config is deliberately left flat/zoned (no weight method, no alias) so the existing
  shipping-zones E2E stays valid; the new features are config-driven and covered by backend
  unit + integration tests.
- **Deferred:** a DB-backed zone/method model + CRUD admin panel + UI (its own slice);
  per-zone weight tables (a method is zone-priced *or* weight-priced, not both at once);
  dimensional/volumetric weight; and an update-variant-weight endpoint (weight is set at
  create; editing reuses the create flow for now).

## Alternatives considered
- *Read weight from a dynamic "weight" attribute* instead of a structured field: rejected —
  it couples shipping to an optional, free-typed attribute with no numeric guarantee. A real
  field is the honest model.
- *Combine zone × weight into a full matrix now:* rejected as premature; mutually-exclusive
  per-method pricing covers the asked-for cases and keeps the value objects simple. The
  matrix can be layered on later behind the same seam.
- *Build the DB zone admin panel in this slice:* deferred per the scope decision — it is a
  separate architectural move (persistence + RBAC + UI) better done as its own slice.
