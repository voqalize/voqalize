# Fernhollow — UI ↔ brain contract (v0)

Fernhollow is a fictional home & furniture store and a Voqalize voice demo. Its agent (today Emily, the
design adviser: voice `omnivoice/emily`, avatar character `emily`, English only — all of it in
`persona.json`, see v5) talks and drives the store's screen. "Emily" below means whoever `persona.json`
names. Design doc: https://claude.ai/artifact/Venfo8c5tvd8u3iG5Jm3zA

This file is the agreement between `frontend/` (React, Vite) and `backend/` (the brain). Both sides build
against it in parallel; change it only by editing this file in the same PR as the code.

## Data

- `data/catalog.json` — the single source of product truth for both sides: 792 products, 32 categories,
  7 rooms (`living, dining, bedroom, home-office, bath, kitchen, decor`). Built by
  `data/build_catalog.py`. Product `id` = URL handle. Images: `images[].file` is `<id>/<n>`; the frontend
  serves them as `/demos/fernhollow/img/<file>-<400|1000>.webp`.
- **No invented product facts.** Nothing outside catalog fields, words in the product's own
  title/intro/highlights/options, authored store policies and authored editorial content. No product dimensions,
  stock levels or delivery dates anywhere in UI or speech — v5 adds the authored size guide (guide-level
  advice only) and the three sample orders' authored delivery slots, and nothing else.

## Brain → UI actions (`session.dispatch`, RTVI `ui-command`)

Every action carries the full payload its component needs (ids AND the display fields), so the page
renders without a second lookup. Product references are catalog `id`s.

| command | payload | UI |
| --- | --- | --- |
| `navigate` | `page`: `home` \| `room/<room>` \| `category/<slug>` \| `product/<id>` \| `journal` \| `journal/<slug>` \| `cart` \| `policy/<topic>` | route change |
| `show_products` | `title, query, product_ids[], count` | listing grid with these products |
| `apply_filters` | `filters{room?,category?,materials[],colours[],styles[],price_min?,price_max?,on_sale?}, product_ids[], count, assumption?` | on the room or category listing (or the shop): each option ringed and ticked in its sidebar, one by one — materials, colours and styles under Made of, Colour and Feel |
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

## v5 — the front of house: one brain, a job per landing page (owner, 2026-11-18)

Fernhollow is now the front of house for every e-commerce agent in the catalogue: one brain, one
character, and a **job** chosen by the page the call starts on. The brain still follows the shopper to
any page and switches job when they land on another job's page.

| landing | job | what the agent does |
| --- | --- | --- |
| `/` | `shop` | furnishes a room within budget, finds, compares, fills the cart (v0–v3) |
| `/returns` | `returns` | opens the order, sets up the return or the swap, waits for the yes (v1, v4) |
| `/size-guide` | `size` | asks about the bed, mattress, room or window; picks the size from the guide; rings it on the product page |
| `/gifts` | `gifts` | turns "for my sister's new flat, under $80" into a short list with a reason each; adds to cart |
| `/orders` | `orders` | says where the parcel is in plain words; moves the delivery day to an authored slot; hands a delivered order to returns |
| `/kiosk` | `kiosk` | the showroom totem: attract screen, three short questions, three picks with reasons, a QR code to the phone |

**Persona in one place.** `persona.json` (character id for `@voqalize/avatar`, display name, role, voice
per language, the languages offered, the default) is read by the brain (`backend/persona.py`) and the page
(`frontend/src/persona.ts`). No name, voice or language is written anywhere else; the authored Markdown
pages write `{{agent}}` for the name.

**`init`** (the connect request's opaque blob): `{surface: "fernhollow-web", landing: "<path>", lang:
"<code>"}`. `landing` is the router path the call started on (`/size-guide`, `/kiosk`…) and picks the
job and the greeting; `lang` is one of `persona.languages` (English only today) and the brain sets both
legs from `persona.voices[lang]` in `on_session_start`. A later `page_viewed` whose path starts with one
of the six landings switches the job; any other page (a product, the cart) keeps it.

**No invented facts, still.** The size guide is authored guide-level advice (`content/size_guide.json`):
which size suits which mattress, where a Small or Large vase sits, rug placement against a sofa,
curtain drop and rod height — plus the general US standard mattress sizes, labelled as the standard.
Nothing states a product's own measurements. Only beds, bedding, vases and faux stems sell a Size
(Queen/King, Small/Large: 59 products); rugs and curtains are sold by fabric, so their sections advise and
pick no size. Delivery days exist only in the three authored sample orders.

### Data

- `content/size_guide.json` — sections (beds, vases, rugs, curtains), the finder's questions (each with
  `when`, the answers it applies under) and the rules that pick a size with the guide's reason.
  `backend/sizing.py` and `frontend/src/sizing/finder.ts` evaluate the same file the same way: the first
  rule whose `if` all hold; the next question is the first whose `when` holds and is unanswered.
- `content/gift_guide.json` — recipients, occasions (category weights), budget chips (30, 50, 80, 100,
  150, 250, 500 dollars) and one authored line per category. `content/kiosk.json` — the kiosk's three
  questions; a feel lists the catalog's own attribute words it means.
- `backend/data/edits.json` — generated by `backend/edits.py` from those and the catalog: for every
  `recipient|occasion|budget` the gift short list (6), for every `room|feel|budget` the kiosk's three,
  each `{product_id, variant_id, reason}`. The page and the brain read this one file, so what is said is
  what is shown. A spoken budget becomes the largest chip at or under it ("under $90" → 80).
- `data/demo_orders.json` — three orders carry a `tracking` block: `FH-31207` packed (can move),
  `FH-31188` on the van (cannot move; `why_not`), `FH-31042` delivered 3 days ago (returnable: the
  returns desk finds it like any demo order). `tracking.events[{stage, days_ago, time, text}]`,
  `tracking.delivery.slot` (the booked slot id), `tracking.slots[{id, days_from_now, window, hours}]`
  (the only days it can move to), `can_reschedule`, `why_not`. Days are relative; the page shows
  `Thu 20 Nov`, the brain says "Thursday 20 November".

### Pages (all work by click alone)

- `/size-guide` — the four sections (anchors `#beds`, `#vases`, `#rugs`, `#curtains`), the **size
  finder** (chips per question, `data-stage-part="size:<question>:<value>"`), its answer card (size +
  reason, or the placement advice), and the sized products of the section with the picked size: each
  card opens `product/<id>?variant=<variant_id>`.
- `/gifts` — the gift edit: recipient, occasion and budget chips
  (`data-stage-part="gift:<control>:<value>"`), the short list with each pick's reason and an Add to cart
  button. A query string `?for=sibling&occasion=housewarming&budget=80` sets the controls.
- `/orders` — "Your orders": the three tracked orders as cards with a status pill; `/orders?order=FH-31207`
  opens one: its lines, a timeline (Ordered → Packed → Out for delivery → Delivered, with the authored
  times), the delivery slot, **Change delivery day** (a list of the authored slots; Save) when it can
  move or `why_not` when it cannot, and for a delivered order **Return or exchange an item** →
  `/returns/start?order=FH-31042`.
- `/kiosk` — a full-screen portrait showroom layout (designed at 1080×1920; on a landscape screen the
  portrait frame is centred and scaled): attract screen → room → feel → budget (big tiles,
  `data-stage-part="kiosk:<question>:<value>"`) → three picks with reasons and a QR code. The QR encodes
  `<origin>/demos/fernhollow/my-picks?ids=<id>,<id>,<id>&from=kiosk`. Start over returns to attract;
  the kiosk also returns there after 90 s untouched on the picks.
- `/my-picks?ids=…` — "Your picks from the showroom": the products with Add to cart, on the phone.

### Stage moves (`frontend/src/stage/scene.json`, spec id `fernhollow`)

Registered once in the app shell (not per page), so a move sent right after a navigation is never
"not on screen": each performer opens its own page first if it is not showing, waits for the part,
rings it, then changes it, and answers one short line. Tool-driven only (no `say`, so no cue verbs).

| move | class | args | does |
| --- | --- | --- | --- |
| `size.answer` | reversible | `question` (kind, mattress, sleepers, room, place, layout, drop), `value` | rings the finder chip and chooses it; `kind` clears the answers under it |
| `gifts.set` | reversible | `recipient?`, `occasion?`, `budget?` (a chip) | rings and sets each control in turn; the list follows |
| `orders.open` | look | `order_number` | opens that order's timeline and rings it |
| `orders.reschedule` | reversible | `order_number`, `slot` | opens the picker, rings the slot, chooses and saves it; refused (with the offered slots) when it cannot move |
| `kiosk.start` | reversible | — | attract → first question |
| `kiosk.answer` | reversible | `question` (room, feel, budget), `value` | rings the tile and chooses it; the third shows the picks and QR |
| `kiosk.restart` | reversible | — | clears the answers, back to attract |

Events (slices `size_finder`, `gift_edit`, `orders`, `kiosk`; all `note`, `by` visitor or agent):
`size.answered{question, value, size?}`, `gifts.changed{recipient, occasion, budget}`,
`orders.opened{order_number}`, `orders.delivery_changed{order_number, slot}`,
`kiosk.screen{screen}`, `kiosk.answered{question, value}`. The brain folds the visitor's into its
mirror (a delivery day the shopper changed by hand is the one it then says).

### Brain tools (new)

- `size_finder(kind, mattress?, sleepers?, room?, place?, layout?, drop?)` — `@needs_result_now`. Sends
  `size.answer` for each answer given (opening `/size-guide`), and returns the guide's size and reason
  with the section's products in that size, or the one next question to ask.
- `pick_size(product, size)` — opens the product page with that Size selected and the options ringed
  (`open_product` with `variant_id`, `focus: "options"`), with the guide's reason. Refused, naming the
  sizes it comes in, when the product has no such size or sells no sizes.
- `gift_edit(recipient, occasion, budget)` — `@needs_result_now`. Sends `gifts.set` (opening `/gifts`)
  and returns the list from `edits.json` with each reason; `add_to_cart` adds a pick.
- `track_order(order_number?)` — `@needs_result_now`. Without a number, the account's three orders in one
  line each; with one, sends `orders.open` and returns where it is in plain words, the booked slot, and
  the slots it can move to (or why not). A delivered order says it can go back and how many days are
  left; `find_order` then opens the returns form (the hand-off).
- `change_delivery(order_number, slot)` — sends `orders.reschedule` for an authored slot; refused when
  the order cannot move or the slot is not offered.
- `kiosk_answer(room?, feel?, budget?)` — `@needs_result_now`. Sends `kiosk.start` (from attract) and
  `kiosk.answer` for each answer given; with all three, returns the three picks and their reasons (the QR
  shows them on the phone); otherwise the next question. `kiosk_restart()` sends `kiosk.restart`.

**Kiosk job:** short turns (one sentence, at most two), one question at a time, the tile names as the
options, never a product that is not one of the three on screen.
