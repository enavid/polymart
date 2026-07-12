# ADR 0050 — Order fulfilment: manual tracking + printable label + BOPIS (Phase 5, fulfilment slice)

- Status: Accepted
- Date: 2026-07-12

## Context
Phase 5 asks for shipping label + tracking and local/in-store pickup (BOPIS). Until now the
order lifecycle stopped at `paid → fulfilled` with no captured shipment, and every order
required a shipping address. Two scope decisions frame this slice:

1. **Tracking is manual, not carrier-integrated.** Staff record a carrier name + tracking
   reference; a real carrier API (buy-a-label, live tracking) is deferred to a future
   provider slice behind a port/adapter. This keeps the slice free of a specific Iranian
   carrier choice and credentials.
2. **BOPIS is a first-class pickup method with its own lifecycle states**, not a reuse of
   the delivery `fulfilled` state — a pickup order is *prepared* then *collected*, which the
   status machine should model.

## Decision
- **Order state machine gains a pickup fork.** New states `READY_FOR_PICKUP` and `PICKED_UP`;
  transitions: `PAID → {FULFILLED, READY_FOR_PICKUP, CANCELLED}`,
  `READY_FOR_PICKUP → {PICKED_UP, CANCELLED}`. A delivery order ships (`FULFILLED`, terminal);
  a pickup order is prepared (`READY_FOR_PICKUP`) then collected (`PICKED_UP`, terminal).
- **`Fulfillment` value object** (carrier, tracking_number, optional tracking_url) — a
  *snapshot* of what staff entered, captured onto the order when it ships (like a line's
  captured price). `Order.ship(fulfillment)` moves `PAID → FULFILLED` and records it;
  `mark_ready_for_pickup()` / `confirm_pickup()` drive the pickup path.
- **Address is now optional on the aggregate.** A pickup order captures no shipping address
  (`shipping_address=None`), mirroring how `shipping`/`tax` are already optional. `CapturedShipping`
  gained an `is_pickup` flag; the shipping context's `ShippingMethod` gained `is_pickup`
  (config `"pickup": true`, a zero-cost method).
- **Checkout forks by method kind.** `PlaceOrder` resolves the address if supplied, quotes the
  chosen method, then: a *pickup* method captures no address; a *delivery* method with no
  address is refused (`UnknownShippingAddressError`). The address requirement moved from
  "always" to "delivery only". The `PlaceOrderSerializer` now rejects only *both* address
  sources (neither is legal for pickup).
- **Staff fulfilment use cases + endpoints** (all `manage_orders`, row-locked via a new
  non-owner-scoped `OrderRepository.get_for_update_any`, audited): `ShipOrder`
  (`POST /orders/<n>/ship/`, refuses a pickup order → 409, captures carrier+tracking),
  `MarkOrderReadyForPickup` (`POST /orders/<n>/ready-for-pickup/`, refuses a delivery order),
  `ConfirmOrderPickup` (`POST /orders/<n>/confirm-pickup/`). A wrong-method or illegal-state
  action is a 409; an unknown order a 404. Audit actions `order.shipped` /
  `order.ready_for_pickup` / `order.picked_up`.
- **Persistence.** Order model gains `fulfillment_carrier`/`_tracking_number`/`_tracking_url`
  and `shipping_is_pickup`; the status column widened to 24; the address columns became
  blank-able. Blank recipient reads back as "no captured address" (pickup); blank carrier as
  "not yet shipped" — the same sentinel pattern the shipping/tax capture already uses. Migration
  `order/0007`.
- **UI.** The order-detail page forks its timeline by delivery kind, shows the captured
  carrier + tracking (a link when a URL is present) once shipped, a pickup note (no address)
  for a pickup order, and staff-only controls (a ship form with carrier/tracking + a "print
  label" link; ready / confirm-pickup buttons). A new printable **shipping-label / packing-slip**
  page (`/manage/orders/<n>/label`) mirrors the pre-invoice proforma. Checkout offers the pickup
  method (a pickup order is placed with no address, even for a signed-in shopper).

## Consequences
- The order lifecycle now models both delivery and pickup end to end, with an immutable
  captured shipment and a durable audit trail for every fulfilment transition.
- Carrier integration is a clean future extension: a `ShippingCarrier` port + adapter can
  populate the same `Fulfillment` snapshot without touching the state machine or the UI.
- **Deferred:** real carrier-API label purchase + live tracking; a dedicated staff fulfilment
  queue (mirrors the refund/card-to-card review debt); a pickup-first checkout UX that skips
  the address step entirely (today a signed-in shopper still passes the address step, but the
  address is not captured for a pickup order); partial/multi-shipment fulfilment.

## Alternatives considered
- *Reuse `fulfilled` for pickup (no new states).* Rejected per the scope decision — a pickup
  order has a meaningful "ready for collection" waiting state that `fulfilled` cannot express,
  and conflating them would lose that operationally important distinction.
- *Integrate a carrier API now.* Rejected — it forces a specific carrier + credentials into a
  slice whose value is the lifecycle and the captured record; the manual path is the smallest
  coherent increment and the port/adapter seam keeps the upgrade cheap.
