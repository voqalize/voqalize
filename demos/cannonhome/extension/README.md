# Javier para Cannon Home — the extension

A Chrome extension that puts Javier, a voice guide, on
[cannonhome.cl](https://cannonhome.cl), Cannon Home's shop of sheets, towels,
duvets, pillows, beds and mattresses. He talks a visitor through the shop in
Spanish or English while he moves their screen: he types in the search box
and reads the dropdown, filters a category by size, colour, thread count and
material, sorts it, opens a product and its specifications or photos, reads
live prices, adds to the bag, takes a guest to the checkout's delivery form
and fills in the delivery details they tell him. One call follows the visitor across every
Cannon Home tab they have open. Everything he shows is the shop's own; the
extension adds a corner widget and the ring he draws around what he is
pointing at.

This is how we show the agent to Cannon Home on their own site, before
anything goes on it; it is not how a customer would ship it.

## What he does

- **Search** (`search_products`): types the query into the site's search box
  at a visitor's pace, lets the dropdown open, and reports its products and
  categories (`search_suggest`); with `open_index`, opens one of them. The
  dropdown visitors see is goPersonal's (`#gp-ac-dropdown`), whose stylesheet
  hides Amasty's; the adapter reads goPersonal's and falls back to Amasty's.
  goPersonal searches as you type, so the report waits for the final query's
  cards.
- **Filter a category** (`filter_listing`): loads the category if needed, then
  applies the quick filters one at a time by their request variable
  (`.qf__group[data-qf-request-var=tamano|color|hilos|material]`) and the
  option's `title`, waits for each AJAX grid, then sorts; reports
  `listing_shown` after every grid, whoever changed it.
- **Open a product** (`open_product`): loads it, opens Descripción,
  Especificaciones or Calificaciones, or steps the gallery; reports
  `product_shown` from the page at once and again from one live
  `POST /graphql` (the page is served from a cache and can be hours old).
- **Read live prices** (`check_prices`): one `POST /graphql` for up to six
  products (`products(filter: {url_key: {in: …}})`), and `route(url:)` for the
  ones that hides (out of stock); reports `prices_read`. Moves nothing.
- **Add to the bag** (`add_to_cart`): on the product's page (opened first if
  needed), sets the quantity with − / +, presses *Agregar*, waits for the bag,
  and reports `cart_state` (lines, count, subtotal and how far from free
  shipping).
- **Show the bag** (`show_cart`): opens or closes the bag drawer.
- **Go to the delivery form** (`start_checkout`): from the bag page (loaded
  first if needed) presses *Terminar pedido*, then, in the login window it
  opens, *Comprar como invitado*, a plain link to `/checkout`; if the window
  does not render its links, it loads that address itself. The move rides
  `sessionStorage` across both loads and finishes on the form.
- **Fill the delivery details** (`fill_checkout`): on `/checkout` (reached as
  above if needed), only the fields the brain sends, in the form's order:
  email, región and comuna (picked from the form's own searchable lists by
  their folded label; the comuna's list loads by AJAX once the región is
  chosen), dirección, número, depto/casa, nombre, apellidos and teléfono (the
  `+56 9` / `+56 2` prefix from the first of the nine digits, the other eight
  in the field). Each is set as a finished edit (native setter, `input`,
  `change`, `blur`, `keyup`: Knockout's bindings need them). Nothing is
  pressed after the fields.
- **Report the form** (`checkout_state`, on load, after a fill and whenever
  the visitor edits it): which fields hold something, never what (only the
  región and comuna names), which required ones are missing, the form's own
  validation messages, whether the email's account brought up a password,
  the delivery methods offered and chosen, and whether the payment step shows.
- His spoken cues (`cue`): open a page, ring a heading or words, open an FAQ.

## What he never does

These are rules of the adapter, not of the prompt, so no brain can lift them:

- He goes as far as the delivery form and never past it. Every click the
  adapter makes goes through one guard (`press` in `src/page.ts`) and every
  page load through another (`go`). Allowed, by structure: the bag page's
  *Terminar pedido* (`[data-role=proceed-to-checkout]` on
  `body.checkout-cart-index`), the login window's guest link
  (`aside.login-modal a[href="/checkout"]`, nothing else in that window), and
  on `/checkout` only the delivery form's región and comuna pickers and its
  phone prefix. Refused wherever they are, before anything is allowed: the
  payment step (`#payment`, `#co-payment-form`), the place-order bar
  (`.co-place-order`, *Completa los pasos*), *Continuar compra*
  (`[data-role=opc-continue]`), the delivery method (the visitor chooses it;
  a store pickup asks for a RUT), the coupon and gift-card boxes, every login
  control (*Iniciar sesión*, Google, *Crear Cuenta*, the password). Every
  other control on `/checkout` is refused too, and so are *Finalizar compra*
  (`#top-cart-btn-checkout`) and any `.action.checkout`. Loads: the bag and
  `/checkout` (only at `#shipping`); every other `/checkout/…` address (the
  order's success page among them), `/customer/account…` and the payment
  returns are refused. Matched by structure first, since Chrome's
  translator rewrites the words, and by the words as well (*Realizar
  pedido*, *Ir a pagar*, *Pagar*, Webpay, …).
- He never logs in and never types a RUT, a password or payment data. The
  brain's `fill_checkout` has no field for any of them, the adapter fills only
  its nine named fields, and `fillField` refuses any field whose name, id,
  autocomplete, placeholder or label says RUT/RUN, password/contraseña,
  card/tarjeta, CVV and the like, or that sits in the payment step. The RUT
  is reported only as filled or missing.
- The hub opens tabs only on cannonhome.cl (the bag and the delivery form,
  never past them or its account pages) and on WhatsApp, which the site links
  as its sales chat.
- Typing an email into the delivery form is the site's own business from
  then on: Magento checks whether it has an account (a password then shows,
  which is the visitor's), and the site's GoPersonal block, whose cart
  reminders are on unless the visitor turns them off, identifies that email
  for them once the address changes. That is what the visitor's own typing
  does too.

## The CSP rule, and why

cannonhome.cl sends an enforced `Content-Security-Policy` (Magento_Csp's long
allow-list) on every page. `content.js` runs in the page's own world, so the
page's policy binds it: its `connect-src` does not list our API, the call's
signalling or the avatar's hosts, and `script-src` does not list the avatar
runtime's host. Left alone, the call could not start. `rules.json` is a
`declarativeNetRequest` rule that **removes** `content-security-policy` and
`content-security-policy-report-only` from `main_frame` responses of
`cannonhome.cl` (which covers `www.`), for the visitor who installed this
preview, on this site only. The site sends no `Permissions-Policy`, so the
microphone needs nothing.

## What is in it

- `src/cannonhome-actions.ts` — the Magento adapter, `window.voqalizeCannonhome
  = {run, context, start, commands}`: the eight moves above plus the cue moves
  (`navigate`, `show_section`, `open_faq`), one at a time (a promise chain),
  and the reporters (`page_changed` with the page's kind from Magento's body
  classes, `product_shown`, `listing_shown`, `search_suggest`, `prices_read`,
  `cart_state`, `checkout_state`, `command_done` / `command_failed`). A move that loads another
  page leaves the rest of itself in `sessionStorage` and the adapter on the
  next page finishes it.
- `src/page.ts` — the waits (never the `load` event, which the site's
  trackers hold back for more than 15 s), the window scroll under the fixed
  marquee bar, the ring in Cannon Home's sale red, typing, the checkout
  guard, and the move left for the next page.
- `src/anchors.ts`, `src/anchor.ts` — Chrome's translator kept off what the
  adapter matches on and reports (headings, filters, product names, the
  specifications, tab titles), from `document_start`.
- `src/narration.ts` — the screen follows his voice: each cue fires when the
  call's spoken text reaches the first words of its sentence; a cue to
  another page fires at once, so the load overlaps his reply.
- `src/hub.ts`, `src/bridge.ts`, `src/background.ts` — the hub: the call's
  relay runs through the extension's service worker, so it reaches tabs on
  both cannonhome.cl and www.cannonhome.cl.
- `src/tabs.ts` — Qween's one-call-every-tab relay, on the hub.
- `src/widget.ts` — the widget, in a shadow root, in Cannon Home's ink and
  sale red, in Lato. It sits bottom-left (WhatsApp owns the bottom-right),
  and moves up or minimises to keep clear of the WhatsApp tab, the bag drawer,
  the filters drawer and the phone's sticky add-to-cart bar. It has no
  microphone glyph, so it is not confused with the search box's own voice
  search (GoPersonal's), which is hidden while a call is live.
- `src/content.ts` — the call: stock pipecat with `@voqalize/client-transport`
  as its media manager, one `sessions.connect` (`surface: "cannonhome-ext"`),
  the avatar, the routing of each Action to the tab in front, and the rejoin
  after every page load with the call's language kept.
- `src/actions.gen.ts` — the Action and event unions, generated from the brain
  with `pnpm gen`. Regenerate after changing either.

The brain is `../backend/`: the prompt, the tools and Cannon Home's knowledge.

## Build and load

```sh
cp .env.example .env          # the agent id and a publishable key (never committed)
pnpm install --ignore-workspace
pnpm gen                      # after any change to the brain's Actions or events
pnpm build                    # → dist/, against dev; `pnpm build:prod` → dist-prod/
```

`pnpm build` reads `.env` (the dev agent and key, `app.dev.voqalize.com`) and
runs the dev avatar runtime. `pnpm build:prod` reads `.env.prod` into
`dist-prod/`, with the npm-pinned runtime. Neither env file is committed.

Load `dist/` unpacked in `chrome://extensions`. The publishable key's allowed
origins are the host pages' (`https://cannonhome.cl`,
`https://www.cannonhome.cl`), because `content.js` runs in the page's world.

## Tests

```sh
pnpm test:e2e
```

Playwright, headless, no network: trimmed copies of the shop's pages
(`test/pages/`, made by `test/make-fixtures.mjs` from pages saved with the
site's scripts run) are served at their real addresses, `/graphql`, the cart
section and the search dropdown are answered with fixed bodies, and the few
site behaviours the adapter leans on (the filter grid's AJAX swap, the
sorter, the dropdown, − / +, the AJAX add and the drawer) are simulated
(`test/site.ts`). The bag's login window and the guest checkout
(`test/pages/login-modal.html`, `test/pages/checkout.html`) were saved from
the live guest checkout with nothing typed and trimmed the same way; the
form's región/comuna lists (the comuna's by AJAX), the phone prefix and its
validation messages are simulated. Each move is driven through `run()` and
its events checked, along with the moves that survive a page load, the guard
that stops at the delivery form, and the fields that are never filled.

## Driving it from the console

With no call, on a Cannon Home page:

```js
await voqalizeCannonhome.run("search_products", { query: "sabanas king", open_index: null });
await voqalizeCannonhome.run("filter_listing", { category_path: "/12-ropa-de-cama/20-sabanas", size: "King", color: "Blanco", threads: null, material: null, sort: "price_asc" });
await voqalizeCannonhome.run("open_product", { path: "/sabanas-2-plazas-300-hilos-liso-fog.html", tab: "especificaciones" });
await voqalizeCannonhome.run("check_prices", { paths: ["/sabanas-king-200-hilos-stone.html"] });
await voqalizeCannonhome.run("show_cart", { open: true });
voqalizeCannonhome.context();
voqalizeCannonhome.start((event, payload) => console.log(event, payload));
```

`add_to_cart` really adds to the visitor's bag; remove the line afterwards.
`start_checkout` and `fill_checkout` really fill the live form: use obviously
fake data, with no email (see above), press nothing, and clear the fields and
empty the bag afterwards.
