# Javier para PC Factory — the extension

A Chrome extension that puts Javier, a voice adviser, on
[www.pcfactory.cl](https://www.pcfactory.cl), pcFactory's store of notebooks,
parts, phones, monitors and everything else with a plug. He talks a visitor
through the store in Spanish or English while he moves their screen: he scrolls
to and rings what he is talking about as he says it, types in the search box,
filters and sorts a listing with its own checkboxes, opens a product and its
specifications, reads live prices and stock by store, compares products on
the store's own comparison page and walks the table row by row, adds to the
cart and takes a guest as far as *Tipo de entrega*. One call follows the
visitor across every pcFactory tab they have open, and through every full page
load, without reconnecting. Everything he shows is the store's own; the
extension adds a corner widget and the ring he draws around what he is
pointing at.

This is how we show the agent to pcFactory on their own site, before anything
goes on it; it is not how a customer would ship it.

## What he does

- **Search** (`commerce.search`): types the query into the header's box
  (`#search-input-desktop`) at a visitor's pace and presses the magnifier,
  which loads `/busqueda-avanzada?search=…`; the move carries across that load
  and reports `listing.shown`. With `open_index` (0 for the first) it rings that
  result and opens it, another load, and reports `product.shown`. pcFactory has
  no suggestions dropdown.
- **Filter a listing** (`filter_listing`, the `{filter: Facet | Option}` cue):
  loads the listing if needed (a category, a search, or a curated list
  `/busqueda?productos=…`), takes off what is asked (`remove`, each with its
  chip's ⊗ under *Filtros*; `clear`, *Limpiar todos*) and any filter on that the
  wish does not have (its chip, in place; a clean load only when there is no
  chip), then for each "Facet: Option" opens the group in the filter panel
  (`h4 > button`, `h3` on a search), rings the option and presses its label,
  and waits for the store's `productos/query` call and the grid; then the price
  range (its two sliders, one after the other), the sort, *Productos por
  página* (`size`: 12, 24 or 32, in place) and the page (`page`: the pager's
  own link, a load the move finishes on). Facets and options go by the page's
  own words (`Marcas`, `RAM`, `Tiendas`), with every option of every facet
  reported (Procesador has 27 on the notebooks); an unknown one is refused with
  what the listing offers, while one the listing offered before and the
  filters on now leave out is a note in the result, not a refusal.
- **A listing is reported only once the store has answered**: while the
  widget redraws (the grid empty, Ordenar por gone, the counter stale, its
  call still out) nothing is reported, and an empty listing only when the
  store's own "Aun no hay productos" / "No se encontraron resultados" shows.
  While one of his moves waits for its grid, the page's watch stays quiet and
  the move reports the settled listing itself (dev calls 31a45613, 8b363867).
- **Sort** (`commerce.sort`, the `{sort: …}` cue): *Ordenar por*
  (`#dropdown-order`), then *Precio menor a mayor*, *Precio mayor a menor* or
  *Recomendados*. Reported as `price_asc`, `price_desc` or `relevance`.
- **Open a product** (`open_product`, `product.tab`): loads `/producto/<id>`,
  then *Sobre este producto*, *Especificaciones* or *Garantía* (`#about-tab`,
  `#specifics-tab`, `#warranty-tab`), the *Disponibilidad* list (stock), or steps
  the gallery (photos). On the product in front, `{tab: zoom}` opens the
  gallery's own window of big photos and steps through a few, `{tab: pickup}`
  opens *Disponibilidad de retiro en tienda* (only a link when some store has
  it) and rings the stores that do, and `{tab: price_note}` presses the ⓘ
  beside *Transferencia / Débito* and reads the store's own words. The windows
  stay open for the visitor and the next move closes them. Reports `product.shown` from the page at once and
  `product.checked` from the store's API (`/productos/{id}`, `/precio`,
  `/stock`): the HTML is cached at the edge.
- **Show** (`{show: …}`): a section heading (the home's *Te recomendamos*,
  *Computación*, *Cupones*…), a specification row by its label on a product
  page (the Especificaciones tab opened first), a store card on /tiendas, a
  coupon card by its code, a product card by its name, a help question, or the
  smallest block with the words; scrolled to the middle of what the header
  leaves, never under it.
- **Questions** (`{faq: …}`): the help centre's questions and the event pages'
  accordions, opened and ringed with their answers.
- **Read** (`find_products`, `check_prices`, `check_stock`): the store's own
  API in the visitor's browser (CORS `*`), nothing on the page moves; on the
  product's own page `check_stock` scrolls to *Disponibilidad* and rings the
  store asked about. Stores are matched by either name the store uses (the
  /tiendas card's, "Mall Cenco Costanera", or the stock list's, "Mall
  Costanera Center"), a comuna or city ("Maipú"), or a zone ("Sur"), accents and
  case folded. Reports `products_found`, `prices_read`, `stock_read`.
- **Stores** (`{store: …}`): on /tiendas, the store's card ringed and its *Ver
  tienda* pressed; the map card's address and hours reported (`store_shown`),
  never the name of the store's manager it also shows.
- **Compare, through the store's own controls** (`compare.add`): first the
  comparator's limits (three at most, one category, read as the comparator
  keeps it), refused in its own words before a box is ticked; then each card's
  own box (`input#product-checkbox<ID>`, never its label, whose click reaches
  the card's link and opens the product), or the product page's *Comparar*,
  opening a product's page to tick it when it is not on the page in front; the
  bar comes up ("Comparador (2/3)"). Then its *Comparar* (`.compare-btn`) is
  ringed, left a beat for the visitor to see, and pressed: the site loads
  `/comparador?prod1=…`, and the move finishes there, reading the table into
  `compare.shown` (each product with its prices; every row with a value, as
  `{group, label, values}`, left to right by the table's own ID row; the rows
  that differ, as *Destacar diferencias* marks them) and ringing it. Only when
  the bar's button is missing is the comparison opened by its address, and the
  detail says so. Products held from before that were not asked for are taken
  out of the bar first.
- **Walk the comparison** (`{compare: Label}`): on /comparador, one row of the
  table scrolled just under the products' cards (which stick under the header)
  and ringed across them; `{compare: diferencias}` switches on *Destacar
  diferencias* and rings the first green row; `{compare: precio}` rings the
  prices. `compare.remove` takes a product out (its ✕ on the comparison page,
  the address rewritten so a reload is honest; on the bar its ✕) or empties
  the comparator with *Limpiar selección*.
- **The menu** (`{menu: Categoría}`): the header's *Categorías* opened and a
  top category's panel shown (hovered, as a visitor does) and ringed; its
  sub-categories reported. Left open; the next move closes it.
- **Cart** (`commerce.cart_add`, `cart_update`, `cart_show`, `apply_coupon`):
  *Agregar al carro* on the product page or a card (no quantity box: on the
  product page the button turns into − / + after the first add, and more go in
  with +; on a card the button is pressed again), the "Producto agregado"
  window left up a moment and closed with *Seguir comprando*; on /carro the
  line's − / +, *Eliminar* and its *¿Confirmas…?*, the coupon box and *Aplicar*
  (the store's own answer is reported). Every change reports `cart.changed`
  (from `localStorage.cartProducts`, priced by the store's `POST /carro/status`),
  whoever made it.
- **Checkout, as far as Tipo de entrega** (`start_checkout`): /carro
  *Continuar* (a load to /checkout), then *Continuar como invitado*, then stops
  on /checkout/tipo-entrega and reports `checkout.changed` with the two
  options. The visitor chooses.

Everything the visitor does themselves is reported too: `page_changed` (the
kind from Modyo's body class), `listing.shown/filtered/sorted` on every grid
change, `product.shown`, `cart.changed`, `checkout.changed`. Chrome's page
translation is kept off what the adapter matches on (`src/anchors.ts`).

## What he never does

These are rules of the adapter, not of the prompt, so no brain can lift them:

- He goes as far as *Tipo de entrega* and never past it. Every click goes
  through one guard (`press` in `src/page.ts`), every page load through
  another (`target`). Allowed, by structure: the cart's *Continuar*
  (`aside.purchase-summary a[aria-label="ir al checkout"]`, on /carro only) and
  the guest card's *Continuar como invitado* on /checkout. Refused wherever
  they are: the header's *Hola, ingresa*, *Inicia sesión*, *Crear nueva
  cuenta*, *Regístrate*, any password field, the delivery radios (`#withdraw`,
  `#dispatch`) and stores, and every other control on /checkout. Loads: /checkout
  and /checkout/tipo-entrega only; every other /checkout/… address, /login,
  /auth, /mi-cuenta, /mis-compras and payment returns are refused, as is any
  other host. Matched by structure first, since Chrome's translator rewrites
  the words, and by the words as well.
- He never logs in and never types a RUT, a password, a card, an address or
  any personal detail: `typeInto` types only in the search box and the coupon
  box, and refuses every other field.
- The service worker opens tabs only on www.pcfactory.cl, never past Tipo de
  entrega, its login or account pages, or a payment.
- While he is on the call, pcFactory's own assistance button
  (`#pcfAssistanceWrapper`, its chat and video advisers) is hidden: one voice
  on the page.
- What is the visitor's own elsewhere on the store is never pressed:
  *Usar mi ubicación actual* on /tiendas (the device's location), the order
  tracking form on /estado-despacho (a RUT and a boleta), a coupon's *Copiar
  código* (the clipboard), the newsletter and business quote forms, and the
  human advisor's button (`offLimits` in `src/page.ts`).

## How the call lives through page loads

pcFactory loads a whole page for every move between pages (a product, a
listing, a search, the cart, the checkout). The call therefore does not live in
a page: it lives in an **offscreen document of the extension** (`call.html`,
"the holder"), which no page load touches. The extension is built on
`@voqalize/stage/extension` (the published `@voqalize/stage` 0.1.0), the host
every site extension shares, and only pcFactory's own parts live here.

- **The holder** (`src/holder.ts`) runs stock pipecat on
  `@voqalize/client-transport`, plays his voice, keeps every open pcFactory tab
  and sends the brain `tabs_changed`, fires his cues as he speaks, sends each
  move to the tab it belongs on, and relays to the pages what they need to draw
  his face. A reply that opens on another page loads it as his voice starts.
  A new tab opens where the move belongs: the cart for cart moves, the listing
  for `filter_listing`, the product for `open_product`, /tiendas for stores.
- **Every page is a follower** (`src/content.ts`): the widget, his face, and
  Stage on the page: the moves `src/pcfactory-actions.ts` registers, made one
  at a time, each ringed before it acts and answered with one `stage_result`.
- **The service worker** (`src/background.ts`) makes the holder on the first
  press of the call button, opens and focuses tabs for his moves, keeps each
  tab's move for its next page and keeps the language choice.
- **The session is minted by the page**, with the publishable key (its fetch
  carries www.pcfactory.cl's Origin), and handed to the holder.
- **A move that loads a page finishes there**, with the same call.
- **The call ends** on End (any tab), when the call drops, or when no
  pcFactory page has been open for 15 s.

A full load on pcFactory takes about 3–4 s before a move can act on the new
page (search → results → product, two loads, took 7 s live).

## No header rule

pcfactory.cl sends no `Content-Security-Policy`, `X-Frame-Options` or
`Permissions-Policy` (checked 2026-10-29 on the home, a listing, a product, the
cart and the checkout), so the avatar runtime, our API and the grant frame's
`allow="microphone"` work in the page as they are. The extension has no
`declarativeNetRequest` rule.

## The widget

pcFactory's palette and face: the header's near-black (#212425) card, the
brand green (#43D87E) for what the visitor presses, Ubuntu; bottom-left,
because the assistance button owns the bottom-right. The ring is pcFactory's
own bright blue (#3F59FA), which holds on white product photos and on the dark
header and comparator bar.

## What is in it

- `src/pcfactory-actions.ts` — the adapter: every move of
  `pcfactory/scene.json`, registered through `scene.registerAll` (a move left
  out does not compile), and the reporters.
- `src/page.ts` — the waits (never `load`), the store's API calls watched, the
  window scroll under the header, typing, and the guard every press, load and
  keystroke goes through.
- `src/site.ts` — who the site is: hosts, language, the widget's words and
  colours, the ring.
- `src/anchors.ts`, `src/anchor.ts` — Chrome's translator kept off the filter
  panel and its chips, product names, tabs, specifications, stock, the
  comparison table, the Categorías menu and store cards.
- `src/holder.ts`, `src/call.html`, `src/call-client.ts`, `src/content.ts`,
  `src/shell.ts`, `src/bridge.ts`, `src/background.ts`, `src/grant.ts`,
  `src/grant.html` — the shared host's entry points, with pcFactory's
  configuration.
- `src/scene.gen.ts` — generated from `../scene.json`; `src/actions.gen.ts` —
  generated from the brain with `pnpm gen`.

The brain is `../backend/`: the prompt, the tools and pcFactory's knowledge.

## Build and load

```sh
cp .env.example .env          # the agent id and a publishable key (never committed)
pnpm install --ignore-workspace
pnpm gen                      # after any change to the brain's Actions or events
pnpm build                    # → dist/, against dev; `pnpm build:prod` → dist-prod/
```

Load `dist/` unpacked in `chrome://extensions`. The publishable key's allowed
origins are `https://www.pcfactory.cl` and `https://pcfactory.cl`.

**The extension id is fixed** (`gifodmamnjemjladnlkfbbijcnhggmdi`):
`manifest.json` carries a `key` (an RSA public key; not a secret), so the
unpacked extension has the same id from any folder and machine, and the
microphone grant holds across rebuilds. The private key is not in the repo and
is only needed to pack a `.crx`.

## Tests

```sh
pnpm test:e2e
```

Playwright, headless, no network.

`test/adapter.spec.ts` drives the adapter on trimmed copies of the store's
pages (`test/pages/`, made by `test/make-fixtures.mjs` from pages saved live
with the site's scripts run), served at their real addresses, with the store's
API answered from bodies saved the same day (`test/pages/api/`) and the few
behaviours of its Vue widgets the adapter leans on simulated (`test/site.ts`).
Each move runs through `Moves.run`, across real page loads where it carries,
with its result and events checked, along with the guard that stops at Tipo de
entrega, the ring before each press, and the translator anchors.

`test/holder.spec.ts` loads the built extension (`VOQALIZE_TEST_BUILD=1`, a
stand-in call and avatar, a made-up API) on pages served at www.pcfactory.cl's
address and checks the port protocol, moves kept across loads, the 15 s rule,
the widget across a page load and the microphone's branches.

## Driving it from the console

With no call, on a pcFactory page:

```js
await __voqalizePcfactory.move("commerce.search", { query: "monitor 27", open_index: null });
await __voqalizePcfactory.move("filter_listing", { category_path: "/categoria/computadores-y-tablets/notebooks/notebooks", filters: ["Marcas: Lenovo", "RAM: 16GB"], min_price: 500000, max_price: 900000, sort: "price_asc" });
await __voqalizePcfactory.move("commerce.filter", ["Marcas", "Lenovo"]);
await __voqalizePcfactory.move("open_product", { path: "/producto/57233", tab: "specs" });
await __voqalizePcfactory.move("page.show", ["Procesador"]);
await __voqalizePcfactory.move("check_stock", { path: "/producto/57233", store: "La Serena" });
await __voqalizePcfactory.move("stores.show", ["Mall Cenco Costanera"]);
await __voqalizePcfactory.move("compare.add", { paths: ["/producto/57695", "/producto/58436"], open: true });
await __voqalizePcfactory.move("compare.show", ["RAM"]);       // on /comparador
await __voqalizePcfactory.move("compare.show", ["diferencias"]);
await __voqalizePcfactory.move("filter_listing", { category_path: "/categoria/computadores-y-tablets/notebooks/notebooks", remove: ["Marcas: Lenovo"], size: 32 });
await __voqalizePcfactory.move("product.tab", ["pickup"]);     // on a product page
await __voqalizePcfactory.move("menu.open", ["Computadores y Tablets"]);
__voqalizePcfactory.moves();
```

`commerce.cart_add` really adds to the visitor's cart and `start_checkout` really
opens the guest checkout: use a cheap item and empty the cart afterwards.
