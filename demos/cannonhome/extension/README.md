# Javier para Cannon Home — the extension

A Chrome extension that puts Javier, a voice guide, on
[cannonhome.cl](https://cannonhome.cl), Cannon Home's shop of sheets, towels,
duvets, pillows, beds and mattresses. He talks a visitor through the shop in
Spanish or English while he moves their screen: he types in the search box
and reads the dropdown, filters a category by size, colour, thread count and
material, sorts it, opens a product and its specifications or photos, reads
live prices, adds to the bag, takes a guest to the checkout's delivery form
and fills in the delivery details they tell him. One call follows the visitor across every
Cannon Home tab they have open, and through every full page load, without
reconnecting. Everything he shows is the shop's own; the
extension adds a corner widget and the ring he draws around what he is
pointing at.

This is how we show the agent to Cannon Home on their own site, before
anything goes on it; it is not how a customer would ship it.

## What he does

- **Search** (`commerce.search`, the `search_products` tool): types the query into the site's search box
  at a visitor's pace, lets the dropdown open, and reports its products and
  categories (`search.suggested`); with `open_index`, opens one of them. The
  dropdown visitors see is goPersonal's (`#gp-ac-dropdown`), whose stylesheet
  hides Amasty's; the adapter reads goPersonal's and falls back to Amasty's.
  goPersonal searches as you type, so the report waits for the final query's
  cards.
- **Filter a category** (`filter_listing`): loads the category if needed, then
  applies the quick filters one at a time by their request variable
  (`.qf__group[data-qf-request-var=tamano|color|hilos|material]`) and the
  option's `title`, waits for each AJAX grid, then sorts; reports
  `listing.shown`, `listing.filtered` or `listing.sorted` after every grid,
  whoever changed it.
- **Open a product** (`open_product`): loads it, opens Descripción,
  Especificaciones or Calificaciones, or steps the gallery; reports
  `product.shown` from the page at once and `product.checked` from one live
  `POST /graphql` (the page is served from a cache and can be hours old).
- **Read live prices** (`check_prices`): one `POST /graphql` for up to six
  products (`products(filter: {url_key: {in: …}})`), and `route(url:)` for the
  ones that hides (out of stock); reports `prices_read`. Moves nothing.
- **Add to the bag** (`commerce.cart_add`, the `add_to_cart` tool): on the product's page (opened first if
  needed), sets the quantity with − / +, presses *Agregar*, waits for the bag,
  and reports `cart.changed` (lines, count, subtotal and how far from free
  shipping).
- **Show the bag** (`commerce.cart_show`, the `show_cart` tool): opens or closes the bag drawer.
- **Change the bag** (`commerce.cart_update`, the `update_cart_item` tool): sets one line, found by its
  product link, to a quantity, or takes it out with 0. In the drawer it presses
  the line's own − / + (each posts by AJAX) or its bin and the *Aceptar* of the
  "¿Seguro…?" window, once Knockout has bound them. On the bag page it sends
  the request those send (`/checkout/sidebar/updateItemQty/` or
  `removeItem/`, with the page's form key) and reloads the page as the page's
  own controls do: live, once the bag page has reloaded, its own − and
  *Quitar* stop answering. The move is checked on the page it loads; from the
  checkout it goes to the bag page first. Reports `cart.changed`.
- **Go to the delivery form** (`start_checkout`): from the bag page (loaded
  first if needed) presses *Terminar pedido*, then, in the login window it
  opens, *Comprar como invitado*, a plain link to `/checkout`; if the window
  does not render its links, it loads that address itself. The move is carried
  across both loads and finishes on the form.
- **Fill the delivery details** (`fill_checkout`): on `/checkout` (reached as
  above if needed), only the fields the brain sends, in the form's order:
  email, región and comuna (picked from the form's own searchable lists by
  their folded label; the comuna's list loads by AJAX once the región is
  chosen), dirección, número, depto/casa, nombre, apellidos and teléfono (the
  `+56 9` / `+56 2` prefix from the first of the nine digits, the other eight
  in the field). Each is set as a finished edit (native setter, `input`,
  `change`, `blur`, `keyup`: Knockout's bindings need them). Nothing is
  pressed after the fields.
- **Report the form** (`checkout.changed`, on load, after a fill and whenever
  the visitor edits it): which fields hold something, never what (only the
  región and comuna names), which required ones are missing, the form's own
  validation messages, whether the email's account brought up a password,
  the delivery methods offered and chosen, and whether the payment step shows.
- His spoken cues, made as his voice reaches their words: open a page
  (`{page: …}`), ring a heading or words (`{show: …}`), open an FAQ
  (`{faq: …}`), and filter or sort the listing in front (`{filter: Tamaño |
  King}`, `{sort: price_asc}`). A filter cue applies one option the way
  `filter_listing` does: it scrolls to the filter bar, opens the filter's pill,
  rings the option, waits a beat, chooses it and waits for the grid; an option
  the listing lacks is refused with the ones it has.

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
- The service worker opens tabs only on cannonhome.cl (the bag and the delivery form,
  never past them or its account pages) and on WhatsApp, which the site links
  as its sales chat.
- Typing an email into the delivery form is the site's own business from
  then on: Magento checks whether it has an account (a password then shows,
  which is the visitor's), and the site's GoPersonal block, whose cart
  reminders are on unless the visitor turns them off, identifies that email
  for them once the address changes. That is what the visitor's own typing
  does too.

## How the call lives through page loads

Magento loads a whole page for most moves (a product, a category, a search
result, the bag). The call therefore does not live in a page: it lives in an
**offscreen document of the extension** (`call.html`, "the holder"), which no
page load touches. The extension is built on `@voqalize/stage/extension`,
the host every site extension shares, and only Cannon Home's own parts live
here.

- **The holder** (`src/holder.ts` → `startHolder`) runs stock pipecat on
  `@voqalize/client-transport`, plays his voice, keeps every open Cannon Home
  tab and sends the brain `tabs_changed`, fires his cues as he speaks (Stage's
  timeline), sends each move to the tab it belongs on, and relays to the pages
  what they need to draw his face. A reply that opens on another page loads
  it as his voice starts (the store takes seconds to load).
- **Every page is a follower** (`src/content.ts` →
  `defineSiteExtension`): the widget, his face, and Stage on the page: the
  moves `src/cannonhome-actions.ts` registers, made one at a time, each ringed
  with the spotlight before it acts and answered with one `stage_result`.
- **The service worker** (`src/background.ts` → `startBackground`) makes the
  holder on the first press of the call button, opens and focuses tabs for his
  moves (only Cannon Home's own pages, never past the delivery form, and
  WhatsApp), keeps each tab's move for its next page and keeps the language
  choice.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries
  cannonhome.cl's Origin, which the key allows) and hands the answer to the
  holder, which connects.
- **A move that loads a page finishes there.** A move sent while a tab loads
  is kept and made on its next page; a move that itself loads a page (a
  product, a listing, the bag, the checkout) carries the rest of itself there
  with the same call, and the next page reports its result.
- **The call ends** on End (any tab), when the call drops, or when no Cannon
  Home page has been open for 15 s.

## The widget across a page load

In a call the widget is back the moment the next page shows, as the last page
left it (the early shell, `src/shell.ts` → `startShell`), with an empty face
slot until the live face has drawn, and the page load is a view transition
under it (`voqalize-javier`). Off a call nothing mounts early.

## The microphone, once

The microphone is the extension's, not cannonhome.cl's: Chrome keeps the
permission against `chrome-extension://<id>`, `chrome.contentSettings` cannot
set it for that origin, and an offscreen document cannot show a prompt. So, on
each press of the call button, the page asks the holder for the extension's
microphone permission state first:

- **granted**: the call starts.
- **prompt** (the first call): the widget shows the extension's own page
  `grant.html` in a frame (`<iframe allow="microphone">`), which asks at once.
  Chrome's prompt names the extension ("Javier para Cannon Home wants to use
  your microphone"); the visitor chooses *Allow*. The holder then reads the
  state again: granted, the call starts. Should it still not be granted (the
  grant was stored for the site rather than the extension, or it was *Allow
  this time*), `grant.html` opens once in a tab of its own, asks the same way,
  closes itself once answered, and the call starts.
- **denied**: the widget says Chrome blocks the microphone for the extension,
  with a button that opens `chrome://settings/content/microphone`, where the
  visitor takes "Javier para Cannon Home" off the blocked list.

## What the visitor sees

The first time: the press, then Chrome's microphone prompt naming the
extension under the widget (and, only if that grant does not hold, a short-
lived tab with the same prompt), then Javier. After that, the press and
Javier. Pages load as they always do; the widget comes back on each new page
already live, his voice carries on across the load, and the moves he started
finish on the page they land on.

**His voice plays from the extension, not from the tab.** Muting the tab
(right-click → Mute site) does not silence him; the widget's *Silenciarme*
mutes the visitor's microphone, and *Colgar* ends the call. Chrome shows the
microphone in use for the extension rather than for the tab.

## The CSP rule, and why

cannonhome.cl sends an enforced `Content-Security-Policy` (Magento_Csp's long
allow-list) on every page. `content.js` runs in the page's own world, so the
page's policy binds it: its `connect-src` does not list our API (the page
mints the session) or the avatar's hosts, and `script-src` does not list the
avatar runtime's host. Left alone, neither could load. `rules.json` is a
`declarativeNetRequest` rule that **removes** `content-security-policy` and
`content-security-policy-report-only` from `main_frame` responses of
`cannonhome.cl` (which covers `www.`), for the visitor who installed this
preview, on this site only. The site sends no `Permissions-Policy`, so the
grant frame's `allow="microphone"` is enough.

## What is in it

- `src/cannonhome-actions.ts` — the Magento adapter: the moves above,
  registered through the scene (`scene.registerAll`) by the ids
  `cannonhome/scene.json` declares: the store's own (`page.open`, `page.show`,
  `page.faq`, `filter_listing`, `open_product`, `product_tab`, `check_prices`,
  `start_checkout`, `fill_checkout`) and the `commerce` kit's
  (`commerce.filter`, `commerce.sort`, `commerce.search`, `commerce.cart_add`,
  `commerce.cart_update`, `commerce.cart_show`); and the reporters:
  `page_changed` with the page's kind from Magento's body classes,
  `prices_read`, and what the screen holds as Stage state events
  (`stage_event`: `product.shown`, `product.checked`, `listing.shown`,
  `listing.filtered`, `listing.sorted`, `search.suggested`, `cart.changed`,
  `checkout.changed`), with only the fields each slice declares and
  `by: "agent"` with the move's `call_ref` when one of his moves made the
  change. Every visible move rings its target before it acts.
- `src/page.ts` — the waits (never the `load` event, which the site's
  trackers hold back for more than 15 s), the window scroll under the fixed
  marquee bar, typing, and the checkout guard every press and load goes
  through.
- `src/site.ts` — who the site is: its hosts, its language, the widget's
  words and colours (Cannon Home's ink and sale red, in Lato, bottom-left), and
  the spotlight's look (3 px of the sale red).
- `src/anchors.ts`, `src/anchor.ts` — Chrome's translator kept off what the
  adapter matches on and reports (headings, filters, product names, the
  specifications, tab titles), from `document_start`.
- `src/holder.ts`, `src/call.html`, `src/call-client.ts` — the holder, and
  the pipecat client it makes.
- `src/content.ts`, `src/shell.ts`, `src/bridge.ts`, `src/background.ts`,
  `src/grant.ts`, `src/grant.html` — the shared host's entry points, with
  Cannon Home's configuration.
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
`https://www.cannonhome.cl`), because the page mints the session.

**The extension id is fixed.** `manifest.json` carries a `key` (an RSA public
key; it is not a secret), so the unpacked extension has the same id from any
folder and on any machine, and the microphone grant made once holds across
rebuilds and moves. The private key is not in the repo and is not needed to
load unpacked (only to pack a `.crx`). `dist/` and `dist-prod/` share the id:
load one of them at a time.

## Tests

```sh
pnpm test:e2e
```

Two suites, Playwright, headless, no network.

`test/holder.spec.ts` loads the built extension (`VOQALIZE_TEST_BUILD=1`
builds it into `test/.build/ext` with a stand-in call,
`test/fake-call-client.ts`, a stand-in avatar and a made-up API) on pages
served at cannonhome.cl's address, and checks the port protocol (the press,
the session minted with the page's Origin and handed over, the state on the
page, its events reaching the brain, mute and End), a move sent while the tab
loads made on its next page's hello, the 15 s rule, the widget across a page
load (in a call the next page has it, as the last page left it, with its
buttons and an empty face slot, two seconds before a page held back by a slow
script has parsed, then the live face fades in, and a view transition reveals the page with the widget as its own
group; off a call nothing mounts early and no transition is asked for; a call
kept for a holder that is gone goes back to the invite), and the microphone's
branches with the permission query stubbed (granted, denied, prompt answered
in the frame, prompt that needs the tab).

`test/adapter.spec.ts` drives the adapter: trimmed copies of the shop's pages
(`test/pages/`, made by `test/make-fixtures.mjs` from pages saved with the
site's scripts run) are served at their real addresses, `/graphql`, the cart
section and the search dropdown are answered with fixed bodies, and the few
site behaviours the adapter leans on (the filter grid's AJAX swap, the
sorter, the dropdown, − / +, the AJAX add and the drawer) are simulated
(`test/site.ts`). The bag's login window and the guest checkout
(`test/pages/login-modal.html`, `test/pages/checkout.html`) were saved from
the live guest checkout with nothing typed and trimmed the same way; the
form's región/comuna lists (the comuna's by AJAX), the phone prefix and its
validation messages are simulated. The adapter runs there on Stage's `Moves`
and spotlight, as in the extension, with a move that loads a page carried in
the tab's `sessionStorage` (`test/entry.ts`). Each move is driven through
`run()` and its result and events checked, along with the moves that survive
a page load, the guard that stops at the delivery form, the fields that are
never filled, the filter and sort cues, and that each press is ringed before
it happens, in Cannon Home's ring.

## Driving it from the console

With no call, on a Cannon Home page:

```js
await __voqalizeCannonhome.move("commerce.search", { query: "sabanas king", open_index: null });
await __voqalizeCannonhome.move("commerce.filter", ["tamano", "King"]);
await __voqalizeCannonhome.move("filter_listing", { category_path: "/12-ropa-de-cama/20-sabanas", size: "King", color: "Blanco", threads: null, material: null, sort: "price_asc" });
await __voqalizeCannonhome.move("open_product", { path: "/sabanas-2-plazas-300-hilos-liso-fog.html", tab: "especificaciones" });
await __voqalizeCannonhome.move("check_prices", { paths: ["/sabanas-king-200-hilos-stone.html"] });
await __voqalizeCannonhome.move("commerce.cart_show", { open: true });
__voqalizeCannonhome.moves();
```

`commerce.cart_add` really adds to the visitor's bag; remove the line afterwards.
`start_checkout` and `fill_checkout` really fill the live form: use obviously
fake data, with no email (see above), press nothing, and clear the fields and
empty the bag afterwards.
