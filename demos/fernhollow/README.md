# Fernhollow Home

A fictional home and furniture store (792 real-looking products, 7 rooms) whose front of house is one
voice agent. The same character, one brain, a job per landing page: the page a call starts on decides
what the agent is there to do, and it follows the shopper anywhere in the store. Everything it drives on
screen also works by click alone; the store is a complete shop without voice.

The agreement between the page and the brain is [CONTRACT.md](CONTRACT.md) (v0 to v5).

## Landing pages and jobs

| page | job | what the agent does |
| --- | --- | --- |
| `/` | shopping assistant | asks about the room one question at a time, builds a whole room within budget on a room board, swaps pieces, compares, finds look-alikes and pieces that go with one, stretches the budget with sale prices, fills the cart and the checkout (the order is placed only on a spoken yes) |
| `/returns` | returns and exchanges | finds the order (a demo order, or one placed in this browser), checks it against the 30-day policy, fills the six-step returns form or sets up the swap to another option value, and submits only on the shopper's yes |
| `/size-guide` | size and fit advisor | asks about the bed and mattress, the room, where a vase goes, how a rug sits with the sofa or how far curtains fall; picks the size from the authored guide, says why, and opens the product in that size with the size ringed |
| `/gifts` | gift finder | turns "something for my sister's new flat, under $80" into the gift edit's short list (recipient, occasion, budget chip), a reason for each pick; adds the one they choose to the cart |
| `/orders` | order tracking | three sample orders (packed, on the van, delivered): says where the parcel is in plain words, moves the delivery day to one of the order's authored slots, and hands a delivered order to the returns desk |
| `/kiosk` | in-store kiosk | a full-screen portrait showroom totem (1080x1920, also fine on a laptop): attract screen, three short questions, three picks with reasons and a QR code that opens the picks on the phone (`/my-picks?ids=…`) |

## Facts the agent may state

Catalog fields and the product's own words, the authored policies (`content/policies.json`), the authored
size guide (`content/size_guide.json`: guide-level advice and the general US standard mattress sizes,
never a product's measurements), the gift and kiosk rules (`content/gift_guide.json`, `content/kiosk.json`)
and the sample orders (`data/demo_orders.json`; the only delivery days in the demo). The gift edit and the
kiosk picks are ranked once by `backend/edits.py` into `backend/data/edits.json`, which the page and the
brain both read, so what is said is what is shown. After changing the catalog or those rules:

```sh
cd demos && uv run python -c "from voqalize_demos.discovery import discover; discover(); \
from voqalize_demos._loaded.fernhollow import edits; edits.main([])"
```

## Run it

```sh
# the store, by click alone (no agent needed)
cd demos/fernhollow/frontend && pnpm install && pnpm dev --port 5401
# with voice: set VITE_AGENT_ID / VITE_PUBLISHABLE_KEY in .env (see .env.example)

# the brain's tests (scripted model, no network)
cd demos && uv run pytest tests/test_fernhollow_e2e.py tests/test_fernhollow_engine.py
```

Add `?debug=1` to any page for the action console: it fires any brain command or Stage move by hand.

## Change the character or add a language

Edit [`persona.json`](persona.json), nothing else:

- `character` is the `@voqalize/avatar` character the page mounts; `name` and `role` are what the agent
  calls itself and what the UI shows ("Talk to Emily"); the Markdown pages write `{{agent}}` for the name.
- `voices` maps each language to the voice that speaks it; `languages` is what the page offers (a toggle
  by the call button appears once there are two); `default_language` is used when the page sends none.

The brain configures both legs (speech recognition and voice) from it in `on_session_start`. Fernhollow is
English only today. To add a language, add its code and voice (check the voice speaks it in the voice
roster first), then translate the greetings in `backend/prompt.py`; the voice-contract row in
`demos/tests/test_demo_voice_contract.py` pins the default pair.
