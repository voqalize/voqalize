# Wanderloom Holidays

A fictional Indian online holiday-package company, and a Voqalize voice demo. A trip planner takes the
trip in a sentence or two ("Delhi to Bali in February, six nights, my wife and I, honeymoon") and builds
the whole holiday on the screen while she talks: round-trip flights, a hotel per city, activities day by
day, transfers and taxes, priced and editable item by item, ending at a review page with a mock payment
the visitor presses themselves.

Everything is invented: the company, the airlines, hotels, experiences and every price
(`data/inventory.json`). Place names and airport codes are ordinary geography.

## Landing pages and the agent's jobs

| Route | What the planner does there |
|---|---|
| `/demos/holidays/` | Helps choose: the nine destinations (Kerala, Goa, Rajasthan, Bali, Dubai, Thailand, Singapore, Maldives, Switzerland) with "from" prices, what is in season, and starts the brief, which takes the visitor to the builder. |
| `/demos/holidays/plan` | Builds the trip: brief → flights → hotels → days → package. Shows the flight options and lets the visitor pick by voice or click, hotels per city with filters ("by the beach"), suggests and adds activities per day within the slot, age and weekday rules, builds the whole package at once, and edits it ("swap the hotel in Ubud for something by the beach", "move a night to Seminyak"). |
| `/demos/holidays/checkout` | Review and pay. The visitor types their details and presses Pay; the planner never pays. `/booked` shows the reference. |

Everything works by click alone; the voice is an adapter over the same store controller. `?debug=1`
opens a console that fires every Stage move by hand.

## How it fits together

- `CONTRACT.md` — the agreement between page and brain: the trip's shape, the engine's rules (prices,
  days and slots, transfers, GST, recommended picks), the Stage moves and the page's events.
- `data/build_inventory.py` → `data/inventory.json` — the inventory both halves read.
- `backend/engine.py` — the rules for the brain; `frontend/src/engine.ts` — the same for the page.
  `data/engine_cases.json` (written by `engine.write_cases()`) holds them to the same answers: vitest
  runs it on the page side, `demos/tests/test_holidays_engine.py` keeps it current.
- `frontend/src/stage/scene.json` — the Stage Spec. Regenerate both halves after editing it, from
  `demos/`:
  `uv run voqalize stage gen holidays/frontend/src/stage/scene.json --py holidays/backend/stage_gen.py --ts holidays/frontend/src/stage/scene.gen.ts`
- `backend/brain.py` — `HolidaysBrain`, an `OpenAIBrain` (GPT-6.1 Terra, medium reasoning). Tools read
  the engine and send Stage moves; the model's words carry `{go:}`, `{step:}` and `{show:}` cues.
- `backend/rejoin.py` — redial (SDK 0.15.0): when the brain's socket drops without a hang-up and
  Voqalize dials again for the same session, the new brain adopts the call held in this process for two
  minutes (trip, page, language, the model's history, the Stage director) and does not greet again.
  See `CONTRACT.md`, "Redial".

## The character and languages: `persona.json`

The one place the character lives, read by the brain (`backend/persona.py`) and the page
(`frontend/src/persona.ts`).

- **To change the character**, edit `character` (an avatar character id), `name`, and each language's
  `voice` in `persona.json`. Nothing else names her.
- **To add a language**, add an entry under `languages` (its BCP-47 tag) with a label, name, voice,
  the two greetings and the switch line, and add the tag to `scene.json`'s `languages`. The voice must
  speak that language (`https://app.voqalize.com/api/v1/catalog.get`).
- English and Hindi today. The visitor picks on the toggle by the call button (`init.lang`); the brain
  configures both legs in `on_session_start`, and switches both mid-call from the toggle or when asked.
  **Aaliyah's voice speaks English only**, so Hindi is read by Ananya's voice (`languages.hi.voice`)
  until an Aaliyah Hindi clip exists; the face stays Aaliyah's.

## Run it

```sh
cd demos/holidays/frontend
pnpm install --ignore-workspace
cp .env.example .env    # VITE_AGENT_ID and VITE_PUBLISHABLE_KEY, to talk; without them it works by click
pnpm dev --port 5408
```

Tests, from `demos/`:

```sh
uv run pytest tests/test_holidays_e2e.py tests/test_holidays_engine.py tests/test_demo_voice_contract.py -q
cd holidays/frontend && pnpm typecheck && pnpm test && pnpm build
```

Data changes: edit `data/build_inventory.py`, then `uv run python holidays/data/build_inventory.py` and
`uv run python -c "import sys; sys.path.insert(0, '.'); from holidays.backend import engine; engine.write_cases()"`
from `demos/`.
