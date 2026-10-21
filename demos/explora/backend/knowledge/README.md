# Explora knowledge

What the Explora voice guide (Javier, on www.explora.com and reservations.explora.com) knows, in three layers. Every fact is the site's own, taken from Explora's English pages and its booking site. Nothing comes from general knowledge. Where the site's pages disagree, the files record each disagreement and which page says what; they do not resolve it.

- **`L1.md`** is always in the prompt, at about 2.5k tokens. It covers:
  - what Explora is
  - each lodge in two lines, with its booking code and page
  - the Travesía, the two lodges opening Dec 2026, and the four expeditions
  - what a stay includes, how explorations work, and the offers and programs
  - how booking works and how to contact Explora (no phone numbers)
  - the site's navigation, including every lodge's sub-page paths
  - the list of L2 topics
- **`L2/<topic>.md`** is read on demand. The file stem is the topic id. Each file opens with `# Title`, then a `Sources:` line naming the page paths it was written from, and ends with "Where the site disagrees with itself". All L2 files are hand-written from L3. There are 19 topics:
  - one per lodge: `atacama`, `uyuni-travesia`, `easter-island`, `sacred-valley`, `torres-del-paine`, `torres-del-paine-reserve`, `patagonia-national-park`, `el-chalten`, `el-calafate`
  - `expeditions-iceland` and `expeditions-south-america`
  - `whats-included`, `explorations`, `offers-and-programs`, `journeys`, `getting-there-and-transfers`, `booking-and-policies`, `conservation-reserves`, `company`
- **`L3/`** holds the generated raw material, which is searchable and highlightable.
  - `pages_main.json`: 150 crawled English pages of www.explora.com. Each record has `{path, url, title, description, kind, h1, sections[{heading, level, tag, selector, heading_selector, text, items[{text, href}]}], faqs[{q, a}], tabs[{selector, click, labels, panes}], ctas, images_alts, text}`. `kind` is one of home, lodge, destination, expedition, experience, offer, about, post or other. Built by `build_main.py`.
  - `lodges.json`: every lodge's and expedition's sub-pages (OVERVIEW, LODGE, EXPLORATIONS, DINING, GETTING HERE, TRAVEL TIPS), with rooms and exploration detail pages. Built by `build_lodges.py`. This file did not exist yet when L1/L2 were written (2026-10-22). Once it lands, re-check the L2 gaps listed below against it.
  - `reservations.json`: the booking site (Art2Fly IBE), explored 2026-10-21. It records:
    - the hotel `<select>` with codes and groups, and which codes book and which only enquire
    - the four steps (paso1 date and nights, paso2 rooms, paso3 contact and payment, the expeditions enquiry form)
    - the inline jQuery UI datepicker and its `lista_disponibles`, the reCAPTCHA rule, deep links, headers and layout
    - recipes for filling fields

## Rebuilding

From `demos/explora/backend/knowledge`. Playwright is not a demos dependency. Both crawlers drive real Chrome (`channel="chrome"`).

    uv run --with playwright python build_main.py              # → L3/pages_main.json (~15 min, ~1 page/s)
    uv run --with playwright python build_main.py --limit 150 --delay 1.0
    uv run --with playwright python build_lodges.py               # → L3/lodges.json, with exploration detail pages
    uv run --with playwright python build_lodges.py --no-details  # skip per-exploration pages
    uv run --with playwright python build_lodges.py --only atacama

Both crawlers, `build_main.py` and `build_lodges.py`, live here in `knowledge/` and write into `L3/`. `reservations.json` was explored by hand; there is no script for it.

A rebuild changes L3 only. When new facts or changed dates appear, update L2 and L1 by hand. Offers carry end dates (for example "book by October 31, 2026"), and expedition departures change each season, so re-read `/offer/` and the departure-date pages on every rebuild.

**Crawl quirks.**
- Some `sections[].text` are shifted by one section: the text belongs to the next heading. Trust the page's `text` field.
- `text` is capped at 6,000 characters.
- Tab and FAQ panes are sometimes cut short.
- `/payment-and-cancellation-policies/`, `/join-the-explorer-echo-society/`, `/what-is-explorer-echo-society/`, `/explora-travels/`, `/transfers-information/`, `/2025/12/02/how-do-we-explore/` and the header and footer navigation were completed from the live pages on 2026-10-21/22.

## Things to know about the site

- **WordPress**, served from www.explora.com. Images are on assets.explora.com.
  - Every link is a **full page load**, including each lodge's sticky sub-menu (`.explora-submenu .secondary-menu a.nav-link`). There is no AJAX router.
  - The page scrolls the **window** (normal document scroll), so `scrollIntoView` works.
  - The **header is fixed** (`header#masthead.site-header.fixed-top`), so scrolled-to content needs a top offset.
  - The body is `#content > div.component-<id>` blocks. There are mobile twins in `.d-md-none` / `.d-lg-none`.
  - Content hides behind tab panels (`.tab-panels-nav li[data-index=N]`, `#v-pills-tab`), "READ MORE / READ LESS" collapses, FAQ accordions and carousels (`‹›`).
  - The language switch covers English / Español / Português / Français / Deutsch (`/es/`, `/pt-br/`, `/fr/`, `/de/`). Only English was crawled.
- **TalkCenter chat.** A chat button and welcome bubble are fixed bottom-right (`#tc-button-container`, `#tc-welcome-message-container`, `#tc-button-mask`). Keep the agent's UI clear of them.
- **Call-tracked phones (CallTrackingMetrics).** Phone numbers are rewritten per visitor, and pages already disagree: the footer shows +1 (855) …, while /explora-contact/ and /explora-passport/ show +1 (800) …. Never quote a phone number. Point to /explora-contact/ or reserve@explora.com. Emails are stable.
- **Booking CTAs** ("CHECK AVAILABILITY", "BOOK NOW") open `https://reservations.explora.com/ibe/paso1?language=EN` in a **new tab** with no lodge selected. `?hotel_code=CODE` preselects one.
- **The booking site** is a different host: server-rendered pages, every step a full page load, no fixed header, window scroll.
  - Changing the lodge reloads the page.
  - Nights load by AJAX after a date is picked.
  - Expedition codes (X…) redirect to an enquiry form with a reCAPTCHA v2 tick box that **the visitor must tick themselves**.
  - Details and selectors are in `L3/reservations.json`.
- **A/B and legacy duplicates are live.**
  - El Chaltén has an older A/B set (`/el-chalten-lodge-ab/`, `/el-chalten-hotel-ab/`, `/el-chalten-tours-ab/`, …). The home page, `/destinations/`, `/lodge/` and `/explora-hotels/` link the A/B overview.
  - Older pages are still reachable: `/atacama-desert-hotels/`, `/atacama-desert-tours/`, `/uyuni-hotel/`, `/uyuni-salt-flat-unique-lodge-jirira-lodge/`, `/easter-island-reserve-hotel/`, `/machu-picchu-hotels/`.
  - Duplicate expedition sets exist (`/tierra-del-fuego-itinenary/`, `/echo-society-travel-tierra-del-fuego/...`, two Sacred Mountains date pages).
  - `/explorations/` redirects to the Torres del Paine explorations page.
  - The menu's "Corporate Travel" link points to `/offer/easter-island-with-complimentary-nights/`, not `/corporate-travel-program/`.
- **Left out on purpose:**
  - the non-English pages
  - the privacy policy body (a WordPress default) and the reporting-channel form
  - most blog posts beyond the 2026 ones and the conservation posts
  - the exploration detail pages (`/explorations/<name>/`), which are for `lodges.json`

## Known disagreements (recorded in the L2 files)

**Counts and dates**
- **Lodge count.** The home page says "nine lodges in Chile, Peru, Argentina, and Bolivia", and elsewhere "nine lodges across Chile, Easter Island, Argentina, and Peru; one overland Travesía into Bolivia". The nine-lodge blog counts Jirira. /explora-jobs/ says "seven destinations across four countries".
- **Exploration counts.**
  - The home page says "more than 30" at each lodge.
  - Torres del Paine: 40+ vs "34 destinations".
  - Atacama: nearly 50 / 49 / 52.
  - Sacred Valley: over 40 / 49.
  - TdP Conservation Reserve: 30+ / 36.
  - Easter Island: 30 / more than 30.
- **Opening of the new lodges.** The booking site says "Opening Dec 2026" and the home page "Opening 2026". The press page writes as if they have opened. El Calafate shows a Gold List 2025 award before opening.
- **Company age.** "Over 30 years", "almost three decades", "more than 20 years" (the founder's letter and the corporate page).

**Money and policies**
- **Policy page.** Its title says "…for year 2021" and its description says changes are free up to 7 days before check-in. The body says 30 days for lodges.
- **Machu Picchu price.** USD 430/380 and USD 400/350, both on the policy page, and US$350 on /corporate-travel-program/. Sacred Valley pages say it is included, extra, or "may" cost extra.
- **Alcohol at Valle Sagrado.** The FAQ says it is not included; "All Meals and Beverages" appears everywhere else.
- **Deposit.** The policy page says up to 30%; the Echo Society terms say 20%.
- **Holiday period.** The policy page gives per-lodge dates; the Echo Society says 21 Dec – 5 Jan. The Echo Society season table is still dated 2022–2023.
- **Expedition cancellation.** The policy page uses a 120/60-day scale; the Tierra del Fuego FAQ uses 60/30.
- **Expedition prices.** Tierra del Fuego is $10,950 vs $10,500, and Sacred Mountains $8,640 vs $7,840. Both lower figures are on the old `/expeditions-call-out-homepage/` block.
- **Expedition dates.** The Sacred Mountains date pages disagree (3 vs 9 departures in 2026; one 2027 date "Sold out" vs "Available"). The Iceland 2027 dates on the departure page differ from the 2027-season post.
- **Tips.** "USD 100 per day per room" on the travel-tips pages vs "$100 per stay per visitor" on the FAQ pages, at several lodges.

**Offers and journeys**
- **Honeymoon windows.** The same page gives two sets of travel dates.
- **Explora Passport.** Lodge pages say "up to 25% on each additional destination"; /explora-passport/ says 10% for Patagonia combinations.
- **Journey cards.** Torres del Paine + Patagonia National Park is $7,000 ("Chilean Patagonia") vs $9,680 ("Pristine Patagonia"). "Lands Of Contrasts" and "South America: Land of Contrasts" are different trips. The same trip is given in "nights" on one page and "days" on another.

**Transfers and lodge facts**
- **Transfers.**
  - Puerto Natales → Torres del Paine: 1.45 h vs 2.5 h vs 1.5–2 h; 112 km vs 140 km.
  - The TdP ↔ El Chaltén van: 8 h vs 8–9 h, and daily vs select days.
  - TdP ↔ El Calafate: 6 h vs 5–6 h.
  - Lodge-to-lodge flight: prices from USD 2,352 (TdP Conservation Reserve page) vs USD 3,384 (Patagonia National Park page).
  - Transfers are "included" on the overviews but "exclusive for programs with transfer included" on the getting-here pages.
- **Altitudes and sizes.**
  - Atacama: 2,500 m / 2,443 m / 2,438 m.
  - Uyuni: 4,700 m vs 3,681 m.
  - Puritama reserve: 6,000 / 6,440 / 7,000 / 8,000 ha.
  - Torres del Paine reserve: 15,000 acres / 14,800 acres / ~6,000 ha. Its share for conservation is 95% vs 97%.
- **Beds.** "King or two double beds" (FAQs) vs "King or 2 twin" (room cards), at several lodges.
- **Patagonia National Park award year** (2025 vs 2024).
- **El Chaltén.** Its travel-tips medical section is copied from Torres del Paine.

## Gaps (things visitors ask that the crawled site does not answer)
- **Prices:** nightly rates outside the booking calendar; single supplements; Travesía prices; spa treatment prices.
- **Not crawled:** the Travesía day-by-day itinerary; the dining pages for Atacama, Sacred Valley, the TdP Conservation Reserve and El Calafate; the LODGE and EXPLORATIONS sub-pages for Easter Island; travel tips for the TdP Conservation Reserve. `lodges.json` may fill these.
- **Not answered by the site:**
  - minimum ages and children's rules for explorations, the Travesía and the expeditions (Iceland Winter recommends 13+)
  - accessibility and reduced mobility
  - dietary needs
  - exact opening days for the two new lodges
  - seasonal closures
  - what happens after an expedition enquiry is sent
  - the current Echo Society season table
