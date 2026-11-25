# Fashio — UI ↔ brain contract

Fashio is an Indian fashion store (prices in INR) on a real product catalogue: the Fashion Product Images
Dataset by Param Aggarwal (MIT, sourced from Myntra). The store brand, its policies and its UI are ours;
the products (names, brands, prices, sizes, descriptions, images) are the dataset's. One agent, whose
character, name, voices and languages live in `persona.json` (today Rohan, English and Hindi), does six
jobs, one per landing page. Both sides build against this file; change it only in the same PR as the code.

## Data

- `data/catalog.json` — the catalogue index, built by `data/build_catalog.py` from the dataset zip and
  uploaded as `catalog/v1/index.json`. 4,623 products. Top level: `credit`, `count`, `types`
  (`<type id>: {label, article, chart: {<gender>: <size chart id>} | null}`), `departments` (the mega
  menu: `{id, label, genders, usage?, sections: [{label, types}]}`), `brands`, `colours`
  (`{<name>: <hex or "conic">}`), `products`. A product row:
  `{id, name, brand, gender (men|women|boys|girls|unisex), type, colour, price (selling, ₹),
  mrp (₹), usage, season, year, sizes: [[label, stock]], scale (alpha|waist|uk|age|one), rank,
  group?, attrs?: {Fit, Pattern, Fabric, …}, model?}`. `group` is the colour-variant group (products
  with the same `group` are one style in other colours). `rank` is the store's Popular order (1 first).
- `catalog/v1/p/<id>.json` (bucket only) — detail: `{id, attributes (all), description: [{heading,
  text}], blurb?, similar: [ids], variants?: [ids], …}`. The product page fetches it; the brain does not
  need it (it answers from the index row).
- `data/store.json` — authored: brand, policies (delivery, changes, cancel_statuses, returns, gift wrap),
  order statuses, size charts, the fit rule's words, campaigns and home rails, gift options, kiosk copy.
- `data/orders.json` — the signed-in customer (Neha Sharma) and her orders; days are offsets from today.
- Nothing is invented at run time: prices, sizes, stock, policies and dates come from these files and
  the rules below, which both sides implement identically (`backend/fashio.py`,
  `frontend/src/data/*.ts`).

### Where the page reads from

Images: `https://storage.googleapis.com/voqalize-fashio-assets/img/<id>/w400.webp` (cards) and
`w1080.webp` (product page, zoom); a missing image falls back to `img/placeholder/w400.webp`. `<img>`
needs no CORS, so images always load straight from the bucket. The catalogue JSON is fetched: on
`voqalize.com` and `dev.voqalize.com` straight from the bucket (its CORS allows GET from those two), on
any other host through the Vite dev/preview proxy at `/demos/fashio/fashio-assets/*` (one function,
`frontend/src/data/assets.ts`). Never a Myntra URL.

## Shared rules

**Search.** A product matches when every set field holds. `dept`: men → gender men|unisex; women →
women|unisex; kids → boys|girls; boys / girls → that gender; ethnic → usage Ethnic; footwear and
accessories → type is in that department's sections; all → anything. `types`, `colours`, `usage`,
`seasons`: membership (colours and brands case-insensitive). `brands`: brand in the list. `sizes`: some
size label in the list has stock > 0. `price_min ≤ price ≤ price_max` (selling price).
`discount_min`: `round((mrp − price) × 100 / mrp) ≥ n`. `query`: every word of 2+ letters appears in
`name + brand + colour + type label` (lowercase). **Order** (`sort`): popular → `rank`; price_asc /
price_desc → price then rank; discount → discount % descending then rank; new → year descending then
rank. Default popular.

**Discount.** `round((mrp − price) × 100 / mrp)`, shown when ≥ 1.

**Stock.** A size with stock 0 is out of stock; 1 to 3 shows "Only N left".

**Fit (Find my size).** Inputs: the product, `usual_size`, `fit` (snug | regular | relaxed, default
regular), `height_cm`. Only for products with scale alpha, waist, uk or age.
1. Base size in the product's scale: the same label when the scale matches (a bare number for a shoe is
   `UK n`); letter ↔ waist through the gender's bottoms chart (women XS 26, S 28, M 30, L 32, XL 34,
   XXL 36, 3XL 38; men XS 28, S 30, M 32, L 34, XL 36, XXL 38, 3XL 40); nothing else converts (ask).
2. The product's cut from `attrs.Fit` (lowercase): a `fit.slim_words` word → slim; a `loose_words`
   word → loose; else regular.
3. Steps: +1 when fit relaxed and cut slim; −1 when fit snug and cut loose; else +1 when `height_cm ≥
   tall_cm` (185) and the type is in `length_types` and the scale is alpha or waist; else 0.
4. Find the base in the product's own size list (a base it does not stock goes to the label nearest by
   the scale's order: alpha XS…4XL, waist by number, uk by number, age by years; a tie to the larger),
   then wanted = the size `steps` places from it along that list, kept inside the list.
5. If wanted is out of stock: the nearest in-stock size by position in the product's size list; a tie
   goes to the larger. The answer names both (`wanted` and `size`).

**Gifts.** Side = `gifts.recipient_gender[recipient]` (women | men | kids | null → any). Pool: products
whose type is in `gifts.ideas[side or "any"]`, gender fitting the side (women: women|unisex, men:
men|unisex, kids: boys|girls, any: all), price ≤ budget (when > 0), in stock. A sized product (scale
not one) only when a size was given and that size is in stock; else one-size only. Score: colour in
`colours` +3, a pattern / material word in `attrs` or the name +2, usage Ethnic for a festive occasion +2,
then rank. Pick the best per type, at most one per type, six in all, best first.

**Bag.** Line key `<product id>|<size>`. Subtotal = Σ price × qty; delivery 0 when subtotal ≥
`delivery.free_over` (799) else `delivery.fee` (79); gift wrap `gift_wrap.price` (49) × qty per gift
line; total = subtotal + delivery + wrap. A placed order's id is `FSH-` + 5 digits (49000 + the
browser's order count), status placed, ETA today + `days_max`.

**Dates (IST).** Today is the date in Asia/Kolkata. An offset `n` is today + n days. Show dates as
`DD MMM YYYY` ("27 Nov 2026"); speak them as "Friday, 27 November".

**Orders.** Status from the data (or this browser: placed at checkout, cancelled here, return
requested here). **After an order is placed its delivery date and delivery address cannot be changed**
(no control for either exists; the agent says so plainly). Cancel is possible only while the status is
in `cancel_statuses` (placed, packed): the agent opens the dialog, the shopper presses Cancel order.

**Returns.** Eligible when the order is delivered, `today − delivered ≤ 7` days (days left = 7 − that),
the item's type is not in `not_returnable_types`, and it was not already returned here. The shopper must
confirm the item is unused and its tags are intact (the two ticks); the agent ticks them only after the
shopper said so. Only the shopper's own click on Submit return sends it. Reference `RTN-<order digits>-
<product id>`.

## Routes and agents (one brain, one job per landing)

| Route | Page | The agent's job there |
| --- | --- | --- |
| `/` | home: campaigns, rails, departments | **shopping** (shopping assistant / site guide) |
| `/shop`, `/shop/<dept>`, `/shop/<dept>/<type>` | listing: filters, sort, grid | shopping |
| `/p/<id>` | product page | **fit** (size and fit advisor) |
| `/compare?ids=a,b` | side by side | shopping |
| `/wishlist`, `/bag`, `/checkout`, `/about` | | shopping |
| `/gifts` | gift finder | **gifts** |
| `/orders` (`?order=<id>`) | orders with tracking | **orders** |
| `/returns` (`?order=<id>`) | returns from an order | **returns** |
| `/kiosk` | full-screen in-store kiosk | **kiosk** |

Persona `roles` label the dock per job. The call's `init` carries `{surface: "fashio-web", page: <path>,
lang: "en"|"hi"}`. The brain starts in the landing's job and follows `screen.viewed` to switch.

## Brain → page

All on-screen moves are **Stage** moves (`frontend/src/stage/scene.json`, generated to
`backend/stage_gen.py` and `frontend/src/stage/scene.gen.ts`; regenerate after editing):
`site.go`, `shop.filter`, `shop.show` (cue `{show: 7421}`), `compare.show`, `product.size`,
`size_chart.open`, `fit.fill`, `fit.recommend`, `wishlist.set`, `bag.add` (confirmed), `bag.gift`,
`checkout.focus`, `gifts.brief`, `gifts.show`, `orders.open`, `orders.cancel_open`, `returns.fill`,
`kiosk.search`, `kiosk.show`, `kiosk.qr`, `kiosk.shortlist`, `kiosk.assist`. Product ids travel as
strings. Each performer rings before it acts, refuses with what the page offers, and returns one short
line.

Markup: `data-stage-thing="product:<id>"` (every product card and the product page's main block),
`data-stage-thing="nav:<path>"` (header links and icons), `data-stage-part="<group>:<value>"` on filter
controls (`dept:women`, `type:kurtas`, `brand:Biba`, `colour:Maroon`, `size:M`, `usage:Ethnic`,
`season:Winter`, `price`, `discount`, `sort`), `size:<label>` on the product page's size buttons,
`fit:height|usual|fit`, `chart-row:<label>`, `add-to-bag`, `wishlist:<id>`, `gift:<id>|<size>`,
`checkout:contact|address|payment|place`, `gifts:<field>`, `order:<id>`, `cancel:<id>`,
`return:item:<id>|reason:<id>|unused|tags|submit`, `kiosk:qr`, `kiosk:assist`. A group the agent
highlights is wrapped in `data-stage-group` so the whole group scrolls into view (X1).

One plain action besides Stage: `language_changed {language}` moves the page's toggle. Its other half is
the typed app event `language_requested {language}` from the call tile's toggle.

## Page → brain

Stage events (`stage_event`), each with `by: visitor|agent`: `screen.viewed {path, page, product_id?,
order_id?, title?}` (silent), `shop.changed {summary, count, …filters, ids}` (first 12 ids),
`product.size_picked`, `fit.changed`, `bag.changed {count, total, lines}`, `wishlist.changed {count,
ids}`, `checkout.changed {contact, address, payment}` (booleans only; what was typed never leaves the
page), `order.placed {order_id, total}` (speaks), `order.selected {order_id, status}`, `order.cancelled
{order_id}` (speaks), `return.changed`, `return.submitted {order_id, reference}` (speaks),
`gifts.changed`, `kiosk.changed`.

## Rules

- Everything works by click alone; the voice layer is an adapter over the same store.
- `?debug=1` shows a console that fires any Stage move by hand and can fake a call.
- Nothing is preselected before the shopper says it (no size, no gift brief, no return reason).
- The shopper types personal data (name, phone, address, payment) and presses the final buttons (Place
  order, Cancel order, Submit return). The agent never asks for, fills or reads back personal data.
- The agent confirms before any change: adding to the bag waits for the shopper's yes to a named
  product and size (`bag.add` is confirmed); a gift note is read back once before it is set.

## Redial (SDK 0.15.0)

On a voice runtime that offers redial (`session.can_redial`), `on_session_start` turns it on. Each live
brain is held in this process by session id (`backend/rejoin.py`, Fernhollow's pattern) while its socket
is up and for two minutes after it closes; a redial on the same process adopts the call as it was (job,
page, language, search, bag and wishlist as last reported, a pending add held for a yes, the gift brief,
the model's history, the Stage director). The rejoined brain does not greet again. A redial that
reaches a fresh process starts a new conversation on the same page.
