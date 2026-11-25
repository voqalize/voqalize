# Fashio — an Indian fashion store with one shopping assistant

Fashio is a demo fashion store, prices in INR, on a real product catalogue: 4,623 products (apparel,
ethnic wear, footwear, bags, watches, jewellery, fragrance) from the **Fashion Product Images Dataset by
Param Aggarwal** ([Kaggle](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset),
MIT licence, sourced from Myntra). The store brand, logo, palette, policies and pages are ours; product
names, brands, prices, sizes, descriptions and images are the dataset's, used as they are. Fashio is a
demo store: it is not Myntra and is not affiliated with any brand shown. Every page carries the credit
in its footer, and `/about` says it in full.

A voice agent (today **Rohan**, from `persona.json`) talks with the shopper and drives the screen with
Stage while he talks.

## Landing pages and the agent's jobs

One brain, one job per landing page; it follows the shopper to another page and switches job.

| Route | Job | What the agent does |
| --- | --- | --- |
| `/demos/fashio/` and every shop page (`/shop…`, `/compare`, `/wishlist`, `/bag`, `/checkout`) | Shopping assistant | Takes a whole request ("a kurta for my sister's mehendi under ₹2,000, she's an M"), sets the listing's filters one by one on screen, names the best products with the card ringed, compares, explains, and adds to the bag after the shopper's yes to a named product and size. Guides checkout without ever asking for personal details: the shopper types them and presses Place order. |
| `/demos/fashio/p/<id>` | Size and fit advisor | Asks the usual size and fit preference (height when length matters), fills the Find my size panel, recommends a size from that product's sizes, cut and size chart, and when that size is out of stock says so and offers the nearest in stock. |
| `/demos/fashio/gifts` | Gift finder | Asks who it is for and the occasion in one breath, then the budget ("or shall I not worry about it?"), then size, colour, pattern or material only if useful; shows a short list with a reason each; gift wrap (₹49) and a note. |
| `/demos/fashio/orders` | Order tracking | Finds the order and reads its tracking. Once placed, an order's delivery date and address cannot be changed; it says so plainly and offers what is possible: cancel before dispatch (the shopper presses Cancel order). |
| `/demos/fashio/returns` | Returns | Only within 7 days of delivery, only unused with the original tags (fragrance is not returnable). Checks the delivery date from the data, asks the shopper to confirm unused and tags on, fills the form, and leaves Submit return to the shopper; refuses politely, with dates, otherwise. |
| `/demos/fashio/kiosk` | Store kiosk | A full-screen in-store screen: voice search of the whole catalogue, a product full screen with a QR code that opens its page (or the shortlist) on the shopper's phone, and a floor assistant on request. |

## Data

- `data/build_catalog.py` reads the dataset zip directly and writes `data/catalog.json` (the index, read
  by the brain and uploaded as `catalog/v1/index.json`) and one detail file per product
  (`catalog/v1/p/<id>.json`: description sections, all attributes, colour variants, similar items) to the
  public bucket `gs://voqalize-fashio-assets` (`--upload`). Its docstring lists the curation: which
  types are kept and dropped, per-type caps picked round-robin across brands, colour-variant grouping,
  size normalisation per article type, and the stock rule.
- **Stock is ours.** The dataset's snapshot marks almost every size unavailable, so each size's stock is
  generated deterministically from the product id and size (about one size in seven out of stock).
- Images are served from the bucket (`img/<id>/w400.webp`, `w1080.webp`, made by a separate job), never
  from the dataset's Myntra URLs; a missing image falls back to `img/placeholder/`. No image is in git.
- `data/store.json` — Fashio's authored policies (delivery, changes, cancellation, returns, gift wrap),
  size charts, campaigns, gift options. `data/orders.json` — the signed-in customer's orders, dated as
  offsets from today (IST), so the return window and tracking stay current.
- `CONTRACT.md` — the page ↔ brain contract: data shapes, the shared rules (search, fit, gifts, bag, dates,
  orders, returns), routes, Stage moves and events.

## How it is built

- `persona.json` — the character: avatar id, display name, the dock's label per job (`roles`), voice per
  language, the languages offered and the default. Read by the page and the brain.
- `frontend/src/stage/scene.json` — the Stage Spec. Regenerate both halves after editing it:
  `uv run --project demos voqalize stage gen demos/fashio/frontend/src/stage/scene.json --py demos/fashio/backend/stage_gen.py --ts demos/fashio/frontend/src/stage/scene.gen.ts`
- `backend/` — `FashioBrain` (`voqalize.sdk.openai.OpenAIBrain`, `reasoning="medium"`), the shared rules
  in `fashio.py`, written lines in `lines.py`, the prompt in `prompt.py`, amounts in speech both ways in
  `spoken.py` (budgets such as "dedh hazaar", "under 2k" reach the model as rupees; an implausible one is
  confirmed back), redial in `rejoin.py`.
- `frontend/` — a standalone Vite + React app on `@voqalize/stage`, `@voqalize/avatar` and
  `@voqalize/client-transport`. The catalogue is fetched from the bucket (through the dev server's
  `/demos/fashio/fashio-assets` proxy on hosts the bucket's CORS does not allow; `src/data/assets.ts`),
  with the same file bundled as a lazy fallback. `?debug=1` opens a console that fires any Stage move by
  hand and can fake a call.
- The agent widget (`frontend/src/voice/`, Paynora's): idle, a bar with the character's still photo, the
  job on this page, EN / हिंदी and the call button; in a call a draggable face tile holds the live
  avatar, the language toggle, mute, minimise and end. No transcript. The language is remembered across
  reloads; drawers and sheets move the agent to a top corner.

## Run it

```sh
cd demos/fashio/frontend && pnpm install --ignore-workspace && pnpm dev --port 5460
# open http://localhost:5460/demos/fashio/  (add ?debug=1 for the move console)
```

For a live call set `VITE_AGENT_ID` and `VITE_PUBLISHABLE_KEY` (see `.env.example`); without them the
store works fully by click. Tests: `cd demos && uv run pytest tests/test_fashio_e2e.py`.
Rebuild the catalogue: `uv run python demos/fashio/data/build_catalog.py --zip <dataset zip> --out <dir> --upload`.

## Change the character or add a language

- **Character:** edit `persona.json` — `character` (an avatar character id), `name`, `role`, `roles` and
  `voices` — and add the idle dock's still photo at `frontend/src/characters/<character>.webp`. Nothing
  else names him: greetings, prompt, UI copy, alt text and tests read the file. Update the voice-contract
  row in `demos/tests/test_demo_voice_contract.py` if the English voice changes.
- **Language:** add it to `languages` and `voices` in `persona.json` (the voice must speak it) and add its
  written lines to every table in `backend/lines.py` (the brain refuses to import without them).

## Redial

A call survives a dropped brain socket (SDK 0.15.0 `Config.redial`): the brain turns redial on where
Voqalize offers it, keeps each call in memory by session id for two minutes after its socket drops
(`backend/rejoin.py`), and the brain a redial starts picks the call up where it was without greeting
again. Details in CONTRACT.md, "Redial".
