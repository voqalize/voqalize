# Fernhollow — UI ↔ brain contract (v0)

Fernhollow is a fictional home & furniture store and a Voqalize voice demo. Emily, the design adviser,
talks (voice **Emily**, `Voice.OMNIVOICE_EMILY`; face: avatar character `emily`; English only) and drives
the store's screen. Design doc: https://claude.ai/artifact/Venfo8c5tvd8u3iG5Jm3zA

This file is the agreement between `frontend/` (React, Vite) and `backend/` (the brain). Both sides build
against it in parallel; change it only by editing this file in the same PR as the code.

## Data

- `data/catalog.json` — the single source of product truth for both sides: 792 products, 32 categories,
  7 rooms (`living, dining, bedroom, home-office, bath, kitchen, decor`). Built by
  `data/build_catalog.py`. Product `id` = URL handle. Images: `images[].file` is `<id>/<n>`; the frontend
  serves them as `/demos/fernhollow/img/<file>-<400|1000>.webp`.
- **No invented product facts.** Nothing outside catalog fields, words in the product's own
  title/intro/highlights/options, authored store policies and authored editorial content. No dimensions,
  stock levels or delivery dates anywhere in UI or speech.

## Brain → UI actions (`session.dispatch`, RTVI `ui-command`)

Every action carries the full payload its component needs (ids AND the display fields), so the page
renders without a second lookup. Product references are catalog `id`s.

| command | payload | UI |
| --- | --- | --- |
| `navigate` | `page`: `home` \| `room/<room>` \| `category/<slug>` \| `product/<id>` \| `journal` \| `journal/<slug>` \| `cart` \| `policy/<topic>` | route change |
| `show_products` | `title, query, product_ids[], count` | listing grid with these products |
| `apply_filters` | `filters{room?,category?,materials[],colours[],styles[],price_min?,price_max?,on_sale?}, product_ids[], count, assumption?` | filter chips + grid |
| `remove_filter` | `key, product_ids[], count` | chip removed |
| `open_product` | `product_id, variant_id?, focus?` (`options`\|`highlights`\|`price`) | product page, focus section ringed |
| `select_variant` | `product_id, variant_id` | variant picker set + ringed |
| `highlight` | `target` (`product:<id>` \| `filter:<key>` \| `slot:<slot>` \| `button:add-to-cart` \| `section:<name>`) | 300 ms spotlight ring |
| `update_brief` | `brief{room?,uses[],materials[],colours[],styles[],budget?}, products_left, asking?{dim, options[]}` | the brief, kept in page state (no bar is shown); `asking` rings the sidebar group holding the options Emily is asking about |
| `show_room_set` | `room, budget, total, pieces[{slot, product_id, variant_id, title, price, compare_at?, image, reason}]` | room board, pieces appear one by one |
| `swap_piece` | `slot, old_product_id, piece{…same as above}, total` | one room-board tile changes |
| `remove_pieces` | `slots[], total` | those room-board tiles taken off, the rest unchanged |
| `show_compare` | `product_ids[], rows[{label, values[], winner?}], summary` | compare board |
| `show_goes_with` | `anchor_id, items[{product_id, reason}]` | goes-with strip |
| `show_more_like` | `anchor_id, items[{product_id, differences[]}]` | look-alike strip with badges |
| `show_savings` | `swaps[{slot, from_id, to_id, was, now}], saved, moved_to?` | savings badges on room board |
| `update_shortlist` | `product_ids[]` | shortlist tray |
| `confirm_add` | `lines[{product_id, variant_id, qty}], label` | confirm prompt on the Add button — the page's own whole-room Add only; Emily adds at once and sends `cart_updated` |
| `cart_updated` | `lines[], total, saved` | cart drawer opens |
| `suggest_finish` | `product_id, reason` | suggestion card in cart |
| `open_policy` | `topic` (`returns`\|`delivery`\|`assembly`\|`care`) | policy panel |
| `undo` | — | revert last screen-changing action |

## UI → brain events (client message / Stage visitor events)

`page_viewed{path}`, `product_viewed{product_id, variant_id}`, `visible_products{product_ids[]}`,
`variant_selected{product_id, variant_id}`, `filter_changed{filters}`, `room_board_edited{slot, action}`,
`cart_changed{lines[], total}`, `confirm_result{confirmed: bool}`, `shortlist_changed{product_ids[]}`.
Every event says `by: "visitor"` when the shopper did it.

## Frontend rule

Every component that an action drives must ALSO work by click/tap alone — the store is a complete,
usable shop without voice. Actions go through one store controller (`src/voice/controller.ts`) so the
voice layer is a thin adapter. A dev-only action console (`?debug=1`) fires any action by hand.

## Returns desk (v1) — a form Emily helps fill, built on Stage

A second experience: `/returns/` (start page) → `/returns/start/` (the form). The shopper starts a
return by voice or by hand; Emily finds the order, checks it against the policy, and fills the form with
them field by field. Data: `data/demo_orders.json` (fictional orders of real catalog products; dates are
`*_days_ago`, so eligibility holds whenever the demo runs; window = `return_window_days`, 30, counted
from delivery; unused items only; an order not yet delivered cannot be returned yet).

**Form steps and fields** (field names are the contract — the page's inputs use them as `name`, the
Stage parts use them as `data-stage-part="<field>:<value>"`):

| step | field | values |
| --- | --- | --- |
| 1 Find your order | `order_number` | e.g. `FH-20418` |
| | `email` | typed by the shopper only — personal data is never a move |
| 2 Items | `items` | line `product_id`s from the order, each with `qty_<product_id>` (1..ordered) |
| 3 Reason | `reason` | `changed_mind`, `doesnt_suit_room`, `arrived_damaged`, `wrong_item`, `not_as_expected` |
| | `condition` | `unused_in_packaging`, `unused_unpacked`, `damaged_on_arrival` |
| 4 Resolution | `resolution` | `refund`, `exchange` (pick another option value of the same product: `exchange_variant_<product_id>`), `store_credit` |
| 5 Collection | `collection` | `pickup`, `drop_off` ; `pickup_window` = `weekday_morning`, `weekday_afternoon`, `saturday` (no dates — no delivery/pickup date promises) |
| 6 Review | — | the shopper presses **Submit return** themselves; Emily never submits |

Confirmation shows a return reference `RT-<order digits>-<n>` and the authored policy lines. Returns
are stored in the browser (localStorage) like demo orders.

**Stage, not custom actions, for this form.** A `scene.json` (Stage Spec, `stage: 1`) in
`frontend/src/stage/` generated for both halves with `uv run voqalize stage gen` (`--py
backend/stage_gen.py --ts frontend/src/stage/scene.gen.ts`) and checked with `voqalize stage check`:

- `returns.open_step` — class `navigate`/`look`, arg `step` (1..6): scrolls to and rings the step.
- `returns.fill` — class `reversible`, args `field`, `value`: rings the input, sets it, returns one short
  line ("reason set to doesn't suit the room"). Refused with the valid options when the value is not one
  of them, or when the field is `email`.
- `returns.select_item` — `reversible`, args `product_id`, `qty`.
- Cues in Emily's words, e.g. `{fill: reason | doesnt_suit_room}` "Let's put down that it doesn't suit
  the room." — the field fills as she says it.
- Slices: `returns_form` (which fields are filled, by name — values only through a brain tool that reads
  what the BRAIN set or what the order data says), state events with `by: "visitor"` when the shopper
  fills/changes a field by hand: `field_filled{field}` as `note`, `step_reached{step}` as `note`,
  `return_submitted{reference}` as `speak` (ask: "thank them and say what happens next, in one line").
- `watch` kit on: dwell on a step with nothing filled for ~12 s is a `speak` event (ask: "offer to fill
  it in, one short line"), never over the visitor.

**Brain tools for returns** (real logic over `demo_orders.json` + `content/policies.json`):
`find_order(order_number)` → order lines + eligibility per line (`eligible` / `outside_window` with days
since delivery / `not_delivered`) — `@needs_result_now`; `start_return(order_number)` → navigate to the
form with the order prefilled; `check_exchange(product_id)` → the product's other real option values.
Everything else is cues.

**Acknowledgement: one, upstream.** Voqalize's own `ack` ("Sure.", "Let me check.") is ON for this
agent (the default) and covers the wait while the brain looks an order up. So Emily NEVER opens a reply
with her own acknowledgement ("Let me check that", "One moment", "Sure!") anywhere in the demo — she
opens on the answer. Tested: no reply's first sentence is an ack phrase.

## v2 — Emily drives everything, and asks when it's unclear (owner, 2026-11-02)

**This is a demo with nothing real behind it, so Emily is not held back.** She can complete checkout
and the returns form end to end. This deliberately overrides Stage's default "paying, consent and
personal data are never moves" for this demo only: values come from what the shopper says, and the
final step (place order, submit return) still needs the shopper's spoken **yes** first (a confirmed
tool, never a cue).

New brain → UI commands:

| command | payload | UI |
| --- | --- | --- |
| `checkout_fill` | `field` (`email, first_name, last_name, address1, address2, city, region, postcode, country, phone, delivery`), `value` | rings the checkout input and sets it; works on the cart → checkout → review flow. Never `email` or `phone`: the shopper types those |
| `checkout_step` | `step` (`contact`, `shipping`, `review`) | moves the checkout to that step |
| `confirm_place_order` | `total`, `label` | confirm prompt on Place order |
| `order_placed` | `order_number`, `total` | confirmation page (demo order, stored like a manual one) |
| `show_choices` | `product_ids[]` (2–4, all on screen), `label` | numbered badges 1..n on those product cards + ring; cleared by `choice_made` or the next navigation |
| `clear_choices` | — | badges removed |

Returns form: `email` may now be filled (a `returns.fill` cue for `email` is allowed), and
`returns.submit` is a confirmed tool after the shopper's yes.

New UI → brain events (all `by: "visitor"`):

- `pointing{product_id, how: "hover"|"focus"|"tap"}` — the product card or product page under the
  pointer/finger/keyboard focus, debounced 300 ms, `silent` (kept for "this one", never spoken about).
- `visible_products{product_ids[], layout: [{product_id, row, col}]}` — now carries screen order, so
  "the one on the left", "the second one", "the bottom row" resolve against what is visible.
- `choice_made{product_id}` — the shopper clicked a numbered product while choices were showing.
- `checkout_changed{field, complete}` / `checkout_step_reached{step}` — field names only, like the returns form; `complete` says the value is usable yet (a whole email, a non-empty field), never what it is. Contact is email and phone only; name and address are on shipping.

**Reference resolution (brain).** Every spoken product reference is resolved against, in order: the
product being pointed at (≤ 5 s old), the products visible on screen (with layout), the shortlist and
room set, then the catalog. Fuzzy title + option matching tolerates transcription noise. If one
candidate is clearly best, use it. If two to four are close — e.g. a listing of similarly named sofas
and a garbled name — dispatch `show_choices` and ask one short question that names the difference
("Which one: one, the oak one on the left, or two, the walnut one?"). Never guess between close
candidates; never ask when one is clearly meant.

## v3 — Show Emily: circle to ask (owner, 2026-11-02)

**Things.** Every selectable element on every page carries `data-fh-thing="<kind>:<id>"` with kind
`product` (catalog id), `category` (slug), `room` (room), `article` (slug). Home: hero photos, room
tiles, on-sale rail, category tiles, journal cards. Listings: cards. Product page: the product, its
look-alike / same-room rails. Articles: inline product cards. Emily's surfaces: room-board pieces,
compare columns, choices. Cart lines.

**Circle to ask.** Hold Shift (desktop) or long-press 350 ms (touch), then draw a loop; a glowing
stroke follows the pointer; things whose box is ≥ 50% inside the closed loop light up while drawing.
On release: numbered badges on the selected things (max 8), a small chip "4 selected · say what you
want" with a clear (×) button, and one event:

- `selection{things: [{kind, id}], gesture: "circle", page}` — `by: "visitor"`, `note`. Cleared by
  `selection_cleared{}` (×, Esc, a new circle, or navigating to another page: the selection is cleared on navigation). Shift + Alt (Option) while circling, or "+ Add more" on the chip on touch, adds to the current selection instead (deduplicated, numbering continues, at most 8) and sends one `selection` with the full set.
- Brain → UI `clear_selection{}`.

**Brain.** "These / those / all of them / the circled ones" resolve to the last selection (ranked
above pointing). Products → compare (2–4), cheapest/attribute questions, add to room set, shortlist;
rooms/categories → navigate/show; mixed or > 4 products for a compare → say what is selected in one
line and ask which to compare. Never act on a selection the shopper did not speak about.

## v4 — Returns that actually work by voice (owner, 2026-11-03)

Found in a live session: (1) orders the shopper placed were invisible to the brain (`find_order` read only
`demo_orders.json`); (2) step 1 (order number + email) was never filled, so steps 2–6 stayed locked and
`returns.submit` was refused; (3) `returns.select_item` refused a valid `qty` ("between 1 and 1") — a
string-vs-number compare; (4) there was no move to advance a step; (5) many turns acted with no words.

**Orders on the client.** Every placed order (by hand or by `order_placed`) is saved in localStorage
`fernhollow-orders`: `{number, email, name, placed_at, lines[{product_id, variant_id, title, variant, qty,
unit_price}], total, status}`. This is a demo store with no delivery, so a placed order counts as
**delivered at the moment it is placed** (eligible for 30 days from then). The returns pages list these
orders first, then the demo orders. The page tells the brain what it holds:

- `orders_known{orders:[…same shape, with placed_days_ago and delivered_days_ago computed…]}` — sent on
  connect and whenever the list changes (`silent`; values are demo data, never personal).

**Brain:** `find_order` searches, in order, orders the brain placed this session, `orders_known`, then the
demo orders; "my last order" / "the order I just placed" means the newest one.

**Form moves (Stage), all `reversible`, all answer with one line:**

- `returns.find` `{order_number, email}` — fills step 1 and looks the order up exactly as the Find button
  does; on success the form moves to step 2; refused with the reason (no such order, email mismatch,
  not delivered, outside window).
- `returns.next_step` `{}` — validates the current step like the Continue button and advances; refused
  naming the missing fields.
- `returns.open_step` `{step}` — jumps back to any step already reached.
- `returns.select_item` `{product_id, qty}` — `qty` is coerced to an integer before validation.
- `returns.fill` `{field, value}` — unchanged; `email` allowed.
- `returns.submit` — confirmed tool after a spoken yes (unchanged).

**Brain tool `prepare_return(order_number, items[{product_id, qty}], reason, condition, resolution,
collection, pickup_window?, exchange_variant?)`** — after the shopper's answers are known, it sends the
whole sequence deterministically with `stage.send(..., queue=False)`: find → select items → next →
reason + condition → next → resolution → next → collection (+ window) → next → review, and reports back
which step it reached and any refusal. Emily asks only for what is missing, one question at a time, then
calls it; she never relies on many spoken cues to fill a form. Every turn that acts also says one line.
