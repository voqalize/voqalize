# Fernhollow Home

A fictional home and furniture store (792 real-looking products, 7 rooms) whose front of house is one
voice agent. The same character, one brain, a job per landing page: the page a call starts on decides
what the agent is there to do, and it follows the shopper anywhere in the store. Everything it drives on
screen also works by click alone; the store is a complete shop without voice.

The agreement between the page and the brain is [CONTRACT.md](CONTRACT.md) (v0 to v6; v6 is the
owner's round-1 review, 19 Nov 2026).

## Landing pages and jobs

| page | job | what the agent does |
| --- | --- | --- |
| `/` | design adviser | leads like a salesperson: remembers every piece the shopper asked for ("a sofa, a rug and cushions") and walks them through it, offering the next step each time; shows each piece in their taste, saves the ones they like, shows the saved picks together (`/saved`), adds them all to the cart and fills the checkout (the order is placed only on a spoken yes). Also builds a whole room within budget, swaps, compares pieces of one kind, finds look-alikes and pieces that go with one |
| `/orders` | orders adviser | every order on the signed-in account; what an order allows depends on its status: packed — change the delivery day or cancel (on a spoken yes); on the way — the ETA and a request for an earlier delivery (a request, not a promise); delivered — start a return |
| `/orders/return?order=…` | returns adviser | the return form of one delivered order (items, reason, resolution, collection, review), filled with the shopper one answer at a time, two ways: what they say is ticked as they say it, what they tap she hears; only the shopper's own press of Submit return sends it (she cannot). Old `/returns…` links redirect here |
| `/gifts` | gift adviser | nothing chosen up front: "Who is it for, and what's the occasion?", then "Do you have a budget in mind, or shall I not worry about it?", then the gift edit's short list with a reason for each pick; adds the one they choose to the cart |
| `/kiosk` | in-store kiosk | a full-screen portrait showroom totem (1080x1920, also fine on a laptop): attract screen, three short questions, three picks with reasons and a QR code that opens the picks on the phone (`/my-picks?ids=…`) |

## Facts the agent may state

Catalog fields and the product's own words, the authored policies (`content/policies.json`), the authored
gift and kiosk rules (`content/gift_guide.json`, `content/kiosk.json`)
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
- `roles` is the label the dock shows under the name on each page, by job (`shop`, `orders`, `returns`,
  `gifts`, `kiosk`): "Design adviser" in the shop, "Returns adviser" on a return form.
- `voices` maps each language to the voice that speaks it; `languages` is what the page offers (a toggle
  by the call button appears once there are two); `default_language` is used when the page sends none.

The brain configures both legs (speech recognition and voice) from it in `on_session_start`. Fernhollow is
English only today. To add a language, add its code and voice (check the voice speaks it in the voice
roster first), then translate the greetings in `backend/prompt.py`; the voice-contract row in
`demos/tests/test_demo_voice_contract.py` pins the default pair.
