# Javier para Agroplanet — the extension

A Chrome extension that puts Javier, a voice adviser, on
[www.agroplanet.cl](https://www.agroplanet.cl), Agroplanet's store of tractor
parts, bearings, batteries, lubricants, tyres, agro-hardware and implements. He
talks a visitor through the store in Spanish or English while he moves their
screen: he scrolls to and rings what he is talking about as he says it, opens
the category menu, types in the search box, filters, sorts and pages a listing
with its own controls, opens a product and its specifications, reads live
prices and stock, fills the cart and takes them to the *Formulario de
cotización*, where he fills what they said yes to and leaves the RUT and
*Crear cotización* to them. Agroplanet sells by quote: there is no checkout
and no online payment. Everything he shows is the store's own; the extension
adds a corner widget and the ring he draws around what he is pointing at.

This is how we show the agent to Agroplanet on their own site, before anything
goes on it; it is not how a customer would ship it.

## What he does

- **Move around the app** (`page.open`, and every move that starts elsewhere):
  agroplanet.cl is one Angular app, so he moves it the way its own links do:
  the page's link to the place when one is on screen (ringed, then pressed),
  else the router itself (`history.pushState` + `popstate`). The move waits
  for the route to draw and finishes in place. Only if the route never draws
  (12 s) does it load the page and carry the rest of the move there.
- **The category menu** (`menu.open`, the `{menu: …}` cue): *Todas las
  categorías* pressed, the level-1 item hovered so its flyout of
  sub-categories opens, both ringed. It stays open until the next move, which
  folds it first; a click of the visitor's elsewhere folds it too.
- **Search** (`commerce.search`): types into `#smartSearchId` at a visitor's
  pace, rings the app's *Sugerencias* when they come (after three letters),
  then presses Enter: `/busqueda/<words>` in place. With `open_index` it opens
  that suggested product instead.
- **Filter, sort, page a listing** (`filter_listing`, `commerce.filter`,
  `commerce.sort`): on a category, search or brand listing, takes off the
  filters asked (`remove`, by unticking their own boxes) or all of them
  (`clear`), then ticks only the options named, one at a time, each panel
  opened first (`app-filter-element`, Material expansion panels that draw
  their options only when open) and each box ringed before it is pressed;
  a filter already on stays on. Then *Ordenar por* (*Menor precio*, *Mayor
  precio*, *Relevancia*) and the page (its own page links; 40 a page). The
  app re-draws the filter panel folded after every change, so what is on is
  read back from the store's answer (`category/getCategory`,
  `search/refineSearch`), never from the boxes. Facets and options go by the
  listing's own words; an unknown one is refused with every option the
  listing offers.
- **Open a product** (`open_product`, `product.tab`): then *Detalle del
  Producto* or *Especificaciones* (its *Ver más* pressed first), steps the
  gallery's thumbnails (photos), opens the main photo's own zoom (zoom), or
  rings the price with *Cotizar* / *Agregar al carro* (price). Reports
  `product.shown` from the page at once and `product.checked` from
  `product/getProductDetail`. A product that says *Confirmar precio en
  tienda* is reported `price_hidden`, with no price.
- **Show** (`{show: …}`): a heading or section title (the home's
  *CATEGORÍAS* and *Aprovecha estas oportunidades en …*, the cart's and the
  quote's cards), the home's banner or brands, a specification row by its
  label, a store card, a product card by its name, a policy panel, or the
  smallest block with the words; under the 64 px sticky header, never under
  it.
- **Questions** (`{faq: …}`): the policy pages' panels (*Cambios y
  devoluciones*, *Despacho*, *Garantía*…) opened with their own header and
  ringed with their answer; a title cut short matches by its start.
- **Read** (`find_products`, `check_prices`, `check_stock`): the store's own
  API in the visitor's browser, with their cookies; nothing on the page
  moves. Stock is one figure per product (`inStock`, `lowStock`); the store
  publishes no stock by store, and says so.
- **Stores** (`stores.show`): on /nuestras-tiendas, the store's card found by
  its name or its city ("La Serena" is the Coquimbo store), the list paged
  with its own page numbers, ringed; its address, phone and hours reported
  (`store_shown`).
- **Cart** (`commerce.cart_add`, `cart_update`, `cart_show`): *Agregar al
  carro* on the product page, then its stepper's + for more; on /carro each
  line's − / + (the app's ids are swapped: `#minus-…` is the +; he goes by
  the icons) and *Eliminar*. Every change reports `cart.changed`, read from
  `minicart/cart/rollover`, whoever made it.
- **Quote** (`start_quote`, `fill_quote`): the cart's *Cotizar*, then on the
  *Formulario de cotización* each field the visitor said yes to (name, phone,
  email, street, number, unit, *Instrucciones*), typed at a visitor's pace
  and left (so Angular validates it), the región and comuna chosen from their
  own lists (the comunas load after the región). Reports `quote.changed`
  with the names of the fields filled and missing, never a value.

Everything the visitor does themselves is reported too: `page_changed` on
every route (the kind from the route), `listing.shown/filtered/sorted` on every
grid change once it has settled (never mid-redraw), `product.shown`,
`cart.changed`, `quote.changed`. Chrome's page translation is kept off what
the adapter matches on (`src/anchors.ts`).

## What he never does

These are rules of the adapter, not of the prompt, so no brain can lift them:

- He never types a RUT, a password or a card: `typeInto` types only in the
  search box and in the quote form's own fields, and refuses the RUT
  (`formcontrolname="rut"`) first, whatever else it is.
- He never presses *Crear cotización*, the header's login (*¡Hola! Inicia
  Sesión*, *Regístrate*), the product page's *Cotizar* (it adds to the cart
  and opens the quote in one press; he adds with *Agregar al carro*), or any
  link off the store (Webpay, the help site, WhatsApp). Every click goes
  through one guard (`press` in `src/page.ts`), every route and load through
  another (`target`): /registrate, /acceso-revision, /perfil, /activar and
  /cotizacion/confirmacion never open, nor does another host.
- The service worker opens tabs only on www.agroplanet.cl, never on those
  pages.

## A single-page app

Agroplanet never loads a page between its routes: the Angular router swaps
the route's component inside `mat-sidenav-content` and pushes the address.
So:

- **The widget stays.** It is mounted on `<body>`, outside `<app-root>`, which
  the app never touches; the call, his face and the page's port live on
  through every route change. (Checked live: the widget's nodes are the same
  after home → category → product.)
- **Every route is a new page to the adapter.** It wraps `pushState` /
  `replaceState` and hears `popstate` (`watchUrl`); on each change it waits
  for the new route to draw what its kind shows, then picks its watchers
  again (a listing's grid, a product, the quote form), reports
  `page_changed` and reads the route's state.
- **Moves finish in place** (`navigate`): no move is carried across a load
  unless the route fails to draw.
- **The store's calls are watched** (`watchApi`): every XMLHttpRequest and
  fetch to `api.agroplanet.cl` is counted while it runs and its answer kept,
  so a move waits for the app's own answer, and a listing is reported only
  when none is out. The adapter's own reads go through the page's original
  `fetch` and never count. On agroplanet.cl something else reading the same
  requests leaves `status` at 0 by `load`, so answers are taken at
  `readyState` 4.
- **The call itself still lives in an offscreen document** (`call.html`, "the
  holder"), as on every site extension built on `@voqalize/stage/extension`
  (0.1.0): so a reload, a typed address or a second tab change nothing on it.

The home opens an empty splash window on every full load of `/` that locks
scrolling; it is closed before any scroll and when a call starts, and the
cookie bar's *Entendido* is pressed when a call starts, so neither covers
what he rings.

## No header rule

agroplanet.cl sends no `Content-Security-Policy`, `X-Frame-Options` or
`Permissions-Policy` (checked 2026-10-29), so the avatar runtime, our API and
the grant frame's `allow="microphone"` work in the page as they are. The
store's API answers CORS for www.agroplanet.cl with credentials, so the
adapter's reads carry the visitor's own cart session.

## The widget

Agroplanet's palette and face: the top bar's near-black (#212121) card, the
brand green (#AECA3A, every action button) for what the visitor presses, with
dark ink for contrast, Roboto; bottom-left, because WhatsApp, the
scroll-to-top square and reCAPTCHA's badge own the bottom-right. The ring is
the site's orange (#E65100, its theme colour), which holds on white, on the
green buttons and on the red menu bar.

## What is in it

- `src/agroplanet-actions.ts` — the adapter: every move of
  `agroplanet/scene.json`, registered through `scene.registerAll` (a move left
  out does not compile), the reporters, and the route watching.
- `src/page.ts` — the waits (never `load`), the router helper, the store's API
  calls watched, the window scroll under the header, typing, the splash and
  cookie bar, and the guard every press, route and keystroke goes through.
- `src/site.ts` — who the site is: hosts, language, the widget's words and
  colours, the ring.
- `src/anchors.ts`, `src/anchor.ts` — Chrome's translator kept off headings,
  panel titles, the menu, the filter panel, product names, specifications,
  store cards and the quote form's labels and options.
- `src/holder.ts`, `src/call.html`, `src/call-client.ts`, `src/content.ts`,
  `src/shell.ts`, `src/bridge.ts`, `src/background.ts`, `src/grant.ts`,
  `src/grant.html` — the shared host's entry points, with Agroplanet's
  configuration.
- `src/scene.gen.ts` — generated from `../scene.json`; `src/actions.gen.ts` —
  generated from the brain with `pnpm gen`.

The brain is `../backend/`: the prompt, the tools and Agroplanet's knowledge.

## Build and load

```sh
cp .env.example .env          # the agent id and a publishable key (never committed)
pnpm install --ignore-workspace
pnpm gen                      # after any change to the brain's Actions or events
pnpm build                    # → dist/, against dev; `pnpm build:prod` → dist-prod/
```

Load `dist/` unpacked in `chrome://extensions`. The publishable key's allowed
origins are `https://www.agroplanet.cl` and `https://agroplanet.cl`.

**The extension id is fixed** (`hkabkfmaedghjhcmnpdddclhjohnjehi`):
`manifest.json` carries a `key` (an RSA public key; not a secret), so the
unpacked extension has the same id from any folder and machine, and the
microphone grant holds across rebuilds. The private key is not in the repo and
is only needed to pack a `.crx`.

## Tests

```sh
pnpm test:e2e
```

Playwright, headless, no network.

`test/adapter.spec.ts` drives the adapter on trimmed copies of the app's routes
(`test/pages/`, made by `test/make-fixtures.mjs` from pages saved live after
the app drew them), served at their real addresses, with the store's API
answered from bodies saved the same day (`test/pages/api/`, filtered and
sorted the way Hybris does) and a cart kept by the test. `test/site.ts`
simulates what the adapter leans on of the app: the router (a link or
`popstate` swaps the route's component without a load), the filter panels, the
sort menu and the pages, the suggestions, the category menu and its flyout,
the stepper, the cart, the quote form's selects and validation, the store
list's pages, the policy panels, the splash window and the photo zoom. Each
move runs through `Moves.run`, with its result and events checked, along with
the guard (the RUT never typed, *Crear cotización* never pressed, the login
and other hosts refused), the ring before each press, the stepper's swapped
ids, the splash closed before a scroll, the watchers picked again on every
route with no load, and the translator anchors.

`test/holder.spec.ts` loads the built extension (`VOQALIZE_TEST_BUILD=1`, a
stand-in call and avatar, a made-up API) on pages served at
www.agroplanet.cl's address and checks the port protocol, moves kept across
loads, the 15 s rule, the widget across a page load and the microphone's
branches.

## Checked live (2026-10-29)

On www.agroplanet.cl, headless Chromium, the adapter bundle injected the way
`content.js` is and the built extension loaded unpacked (its console handle,
the widget bottom-left and outside `<app-root>`, kept across routes):

- home: `page.show` *CATEGORÍAS* and *Aprovecha estas oportunidades en
  Octubre*, the brands; the splash window closed first; `menu.open`
  *Repuestos De Tractor* and *Baterías* (flyout up, folded by the next move);
- `page.open` /categoria/lubricantes/AG100 in place (no load), then
  `commerce.filter` Marca LUBRITEK (4 products), `commerce.sort` price_asc;
  `filter_listing` LUBRITEK + MOBIL + price_desc, `remove`, `clear`,
  `page: 2`; listing reports only once settled;
- `commerce.search` "bateria" (suggestions, Enter, 88 results), and with
  `open_index` (the suggested product opened in place);
- `open_product` 1173221 with specs, details, photos, price, `page.show`
  *País*; zoom on 141492; the hidden price of 139083 reported as hidden;
  `check_prices`, `check_stock` (asked "La Serena" → Coquimbo),
  `find_products` (bateria + DGP + price_asc; category AG100);
- `commerce.cart_add` 2 (Agregar al carro, then +), `cart_show`,
  `cart_update` 3 then 1 (by the stepper), `start_quote`, `fill_quote` with
  test data (Prueba Voqalize, 912345678, prueba@example.com, Metropolitana,
  Santiago → "Santiago centro", Test, 1): every control valid but the RUT,
  which stayed empty; *Crear cotización* stayed disabled and was never
  pressed; then `cart_update` 0 emptied the cart;
- `stores.show` Osorno (page 2 of the list) and La Serena; `page.faq`
  *Garantía Legal* on /cambios-devoluciones.

## Driving it from the console

With no call, on an Agroplanet page:

```js
await __voqalizeAgroplanet.move("page.open", { path: "/categoria/lubricantes/AG100" });
await __voqalizeAgroplanet.move("filter_listing", { category_path: "/categoria/lubricantes/AG100", filters: ["Marca: LUBRITEK"], sort: "price_asc", page: null });
await __voqalizeAgroplanet.move("commerce.filter", ["Marca", "LUBRITEK, MOBIL"]);
await __voqalizeAgroplanet.move("commerce.search", { query: "bateria", open_index: null });
await __voqalizeAgroplanet.move("menu.open", { category: "Repuestos De Tractor" });
await __voqalizeAgroplanet.move("open_product", { path: "/producto/aceite_lubritek_utf_semisintetico_19l/1173221", tab: "specs" });
await __voqalizeAgroplanet.move("stores.show", { name: "Osorno" });
await __voqalizeAgroplanet.move("page.faq", { question: "Garantía Legal", path: "/cambios-devoluciones" });
__voqalizeAgroplanet.moves();
```

`commerce.cart_add` really adds to the visitor's cart (an anonymous one, kept
by a cookie) and `fill_quote` really types into the quote form: use a cheap
item, never press *Crear cotización*, and empty the cart afterwards.
