# Fernhollow — UI ↔ brain contract (v0)

Fernhollow is a fictional home & furniture store and a Voqalize voice demo. Mira, the design adviser,
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
| `update_brief` | `brief{room?,uses[],materials[],colours[],styles[],budget?}, products_left` | room-brief chips |
| `show_room_set` | `room, budget, total, pieces[{slot, product_id, variant_id, title, price, compare_at?, image, reason}]` | room board, pieces appear one by one |
| `swap_piece` | `slot, old_product_id, piece{…same as above}, total` | one room-board tile changes |
| `show_compare` | `product_ids[], rows[{label, values[], winner?}], summary` | compare board |
| `show_goes_with` | `anchor_id, items[{product_id, reason}]` | goes-with strip |
| `show_more_like` | `anchor_id, items[{product_id, differences[]}]` | look-alike strip with badges |
| `show_savings` | `swaps[{slot, from_id, to_id, was, now}], saved, moved_to?` | savings badges on room board |
| `update_shortlist` | `product_ids[]` | shortlist tray |
| `confirm_add` | `lines[{product_id, variant_id, qty}], label` | confirm prompt on the Add button |
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

## Returns desk (v1) — a form Mira helps fill, built on Stage

A second experience: `/returns/` (start page) → `/returns/start/` (the form). The shopper starts a
return by voice or by hand; Mira finds the order, checks it against the policy, and fills the form with
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
| 6 Review | — | the shopper presses **Submit return** themselves; Mira never submits |

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
- Cues in Mira's words, e.g. `{fill: reason | doesnt_suit_room}` "Let's put down that it doesn't suit
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
agent (the default) and covers the wait while the brain looks an order up. So Mira NEVER opens a reply
with her own acknowledgement ("Let me check that", "One moment", "Sure!") anywhere in the demo — she
opens on the answer. Tested: no reply's first sentence is an ack phrase.
