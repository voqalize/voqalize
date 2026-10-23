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
- **Change the bag** (`update_cart_item`): sets one line, found by its
  product link, to a quantity, or takes it out with 0. In the drawer it presses
  the line's own − / + (each posts by AJAX) or its bin and the *Aceptar* of the
  "¿Seguro…?" window, once Knockout has bound them. On the bag page it sends
  the request those send (`/checkout/sidebar/updateItemQty/` or
  `removeItem/`, with the page's form key) and reloads the page as the page's
  own controls do: live, once the bag page has reloaded, its own − and
  *Quitar* stop answering. The move is checked on the page it loads; from the
  checkout it goes to the bag page first. Reports `cart_state`.
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
**offscreen document of the extension** (`call.html`, `src/holder.ts`, "the
holder"), which no page load touches.

- **The holder** runs stock pipecat on `@voqalize/client-transport`, plays his
  voice, keeps every open Cannon Home tab (by browser tab id: its port, where
  it is, whether it is in front) and sends the brain `tabs_changed`, routes
  each brain Action to the tab it belongs on, fires his cues as he speaks
  (`src/narration.ts`) and relays to the pages what they need to draw his
  face (`src/relay.ts`: pipecat's events, the avatar's sync channel, which the
  holder opens and says hello on, and the mouth clock).
- **Every page is a follower** (`src/content.ts`): the widget, his face
  (the unchanged avatar against a stand-in client fed by the relay,
  `src/follow.ts`), the site adapter, and the moves the holder sends it. It
  reports what it shows up the port. Each page keeps one port to the holder
  (`src/bridge.ts` in the isolated world, `src/hub.ts` in the page's world).
- **The service worker** (`src/background.ts`) makes the holder on the first
  press of the call button, with the reasons `USER_MEDIA` and `WEB_RTC` (they
  keep the document alive through any silence; `AUDIO_PLAYBACK` alone closes
  it after 30 s without sound), one at a time, and tells every Cannon Home
  tab when it is up (`holder-up`): a port opened before the holder existed has
  no one at the other end, so pages open theirs on that word. It also opens and
  focuses tabs for his moves (an offscreen document has no `chrome.tabs`) and
  keeps the language choice.
- **The session is minted by the page.** On the call button the page calls
  `sessions.connect` with the publishable key (its fetch carries
  cannonhome.cl's Origin, which the key allows; a `chrome-extension://` origin
  cannot be added to a publishable key) and hands the answer to the holder,
  which connects.
- **A move for a page that is loading waits for it.** When a page starts
  loading another document it tells the holder (`leaving`); a move sent to
  that tab meanwhile is kept and delivered when the next page says `hello`.
  A move that itself loads a page finishes there (the adapter's
  `sessionStorage` leftover, as before).
- **The call ends** on End (any tab), when the call drops, or when no Cannon
  Home page has been open for 15 s; the holder then closes. Reloading or
  updating the extension ends it too.

## The widget across a page load

The call outlives a page load, and in a call the widget does too, as near as a
page can: it is back the moment the next page shows, not once the page has
parsed and Magento's scripts have run (that wait was 1 to 3 s with no widget
and no face).

- **What the page leaves.** While a call is on, `content.js` keeps a picture of
  it in the tab's `sessionStorage` (`src/persist.ts`): live or connecting,
  muted or not, the status line, the language, where the visitor put the widget
  and whether it is minimised, the character's still, and the last frame his
  face drew (read from the avatar's canvas every 3 s and as the page leaves).
  It is taken away when the call ends, and is stale after 60 s.
- **The early shell.** `shell.js` (`src/shell.ts`) runs in the page's world at
  `document_start`, before any of the page's scripts. Off a call it reads that
  one key and does nothing else. In a call it mounts the widget on `<html>` at
  once, as the last page left it, with the last frame of his face as a still
  where his face goes. `content.js` (still at `document_idle`) adopts that
  widget instead of mounting another, asks the holder for the call's state as
  before, starts building his face at once (`preloadAvatar`), and fades the
  still out once the live face has drawn. Should the holder be gone (no
  holder, or no word from it in 8 s), the carried widget goes back to the
  invite.
- **The view transition.** In a call both pages opt in to a cross-document
  view transition (`@view-transition { navigation: auto }`, Chrome 126+): the
  page that leaves (`content.js`, while a call is on) and the page that arrives
  (`shell.js`, from what was kept). The widget's host has its own
  `view-transition-name` (`voqalize-javier`), so the page fades under it in
  150 ms while it stays where it is. The host is a see-through, fixed box over
  the viewport that takes no pointer events (the widget inside it does), so it
  is captured whole and in place. Older Chrome ignores the rule and loads the
  page as before, with the widget still up early. Off a call no transition is
  asked for.

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
- `src/holder.ts`, `src/call.html` — the holder: the call, his voice, the
  tab registry, the routing of each Action, the moves kept for loading tabs,
  the 15 s rule (above); `src/call-client.ts` makes the pipecat client and
  reads the microphone permission.
- `src/relay.ts`, `src/follow.ts` — what crosses from the holder to the pages
  for his face, and the stand-in client the avatar draws against.
- `src/narration.ts` — the screen follows his voice: each cue fires when the
  call's spoken text reaches the first words of its sentence; a cue to
  another page fires at once, so the load overlaps his reply. It runs in the
  holder, so a load ends nothing.
- `src/protocol.ts` — the messages between the pages, the holder and the
  service worker.
- `src/bridge.ts`, `src/hub.ts` — the page's port to the holder and its
  requests of the service worker.
- `src/background.ts` — the service worker (above).
- `src/grant.ts`, `src/grant.html` — the extension's one-time microphone
  grant (above).
- `src/widget.ts` — the widget, in a shadow root, in Cannon Home's ink and
  sale red, in Lato. It sits bottom-left (WhatsApp owns the bottom-right),
  and moves up or minimises to keep clear of the WhatsApp tab, the bag drawer,
  the filters drawer and the phone's sticky add-to-cart bar. It has no
  microphone glyph, so it is not confused with the search box's own voice
  search (GoPersonal's), which is hidden while a call is live. It also holds
  the grant frame and the "microphone blocked" message.
- `src/shell.ts`, `src/persist.ts` — the early shell, what a page in a call
  leaves for the next one, and the view transition (above).
- `src/content.ts` — the page: the widget, his face, the adapter, the moves
  the holder sends, and on the call button the microphone check and
  `sessions.connect` (`surface: "cannonhome-ext"`).
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
load (in a call the next page has it, as the last page left it and with the
kept frame of his face, two seconds before a page held back by a slow script
has parsed, and a view transition reveals the page with the widget as its own
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
