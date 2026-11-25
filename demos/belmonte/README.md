# Hotel Belmonte

The mobile guest app of a fictional coastal resort in Halcyon Bay, California, and a Voqalize voice
demo. Everything a guest would phone the front desk for is done in the app, with a concierge who talks
and drives the screen: she checks you in, orders food and drinks to your room or pool cabana, books the
spa, activities and meeting rooms, opens a visitor's request at the front desk, sends housekeeping and
the other front desk requests, reads the folio and arranges late or express check-out, and answers house
rules from the hotel's own information. The guest presses the final button wherever money is charged or
someone is approved.

Everything is invented: the hotel, the guest, the menus, prices, slots and policies
(`data/hotel.json`). US English, USD, °F, US dates and times.

## The phone frame

On a desktop or tablet the app runs inside an iPhone-style device (dynamic island, status bar, home
indicator) on a branded backdrop with the caption "Hotel Belmonte guest app, a Voqalize demo" and the demo
scenario switch. On a real phone (≤ 700 px wide, or ≤ 620 px tall) the frame's chrome goes and the app is
the whole screen. It is one document, no iframe: the app lives in `#screen`, which is the containing block
for everything fixed inside it (`transform`), so the concierge's widget, the sheets and the toast stay
inside the phone; the one scroll area is `#app-scroll`, and the concierge's rings are brought
fully into view inside it (`frontend/src/stage/view.ts`).

## Landing pages and the concierge's jobs

One concierge, one mode across the app; she follows the guest between tabs. The tab bar is Home, Dining,
Experiences, Requests, Stay.

| Route (under `/demos/belmonte`) | What she does there |
|---|---|
| `/` Home | Greets by name, check-in (arrival day) or the key and check-out (last morning), tonight's events, every service. |
| `/stay/check-in` | Confirms the reservation, waits for the guest's own ID scan, sets arrival time and room preferences (floor, bed, quiet) and says the room they get, offers early check-in with its fee; the guest presses Complete check-in and gets the digital key. |
| `/stay/check-out` | Reads the folio, explains a charge, questions one with the guest's reason, late check-out options and fees, express check-out the guest presses. |
| `/dining`, `/bar` | Menus by meal period or bar section with prices, choices, diet and allergens; adds items with every choice the guest made (asks for missing ones), the order with service charge, delivery, tax and tip, cabana or room; 21+ rule for alcohol. |
| `/spa` | Treatments, free times by day and therapist preference, picks the time; cancellation policy; the guest presses Book. |
| `/activities` | Pools, kids club, golf, tennis, fitness classes, tours, live music tonight, pinned on the resort map; sets up a booking. |
| `/meetings` | Rooms that fit a headcount and layout, free blocks, a full quote with catering and AV. |
| `/visitors` | Who is waiting at the desk; opens a request with where to meet; adds an expected visitor. |
| `/requests` | Housekeeping, maintenance, wake-up call, the car from valet, a ride, lost and found. |
| `/info` | House rules, pets, smoking, pools, Wi-Fi, parking, quiet hours, accessibility, contact. |

Everything works by tap alone; the voice is an adapter over the same store controller
(`frontend/src/state/store.ts`). `?debug=1` opens a console that fires every Stage move by hand and fakes
the in-call widget's states.

## The concierge's widget (`frontend/src/voice/Widget.tsx`)

One entry point, no transcript. By default, before and during a call, she is a circle with her face (the
still photo when idle, the live avatar in a call), with a subtle ring while she listens or speaks. A tap
or click expands it: before a call to her name, her job on this tab and Talk; in a call to a larger face
with exactly two buttons, Mute and End. There is no minimise button: after 4.5 seconds untouched it folds
back to the circle by itself (a tap on the face or Escape folds it at once). It sits bottom right above
the tab bar, takes another corner when a guest-only or primary button (`data-dock-avoid`) would be under
it, and moves to the top right while a sheet is open, so it never covers the tab bar or a sheet's main
button. The face button carries `aria-expanded` and a label naming her and the call's state.

## How it fits together

- `CONTRACT.md` — the agreement between app and brain: data, the rules, the moves, the events, the call.
- `data/build_data.py` → `data/hotel.json` — read by both halves.
- `backend/hotel.py` and `frontend/src/lib/rules.ts` — the same rules twice; `data/rules_cases.json`
  (written by `hotel.write_cases()`) holds them to one answer.
- `frontend/src/stage/scene.json` — the Stage Spec. Regenerate both halves after editing it, from `demos/`:
  `uv run voqalize stage gen belmonte/frontend/src/stage/scene.json --py belmonte/backend/stage_gen.py --ts belmonte/frontend/src/stage/scene.gen.ts`
- `backend/brain.py` — `BelmonteBrain`, an `OpenAIBrain` (GPT-6.1 Terra, medium reasoning). Reads are
  `needs_result_now`; actions return at once, and one that cannot be done is said straight away.
- `backend/rejoin.py` — redial: a dropped socket's call is adopted by the redialled brain for two minutes.

## The character and language: `persona.json`

The one place the character lives, read by the brain (`backend/persona.py`) and the app
(`frontend/src/persona.ts`).

- **The concierge is Kasia** (the holidays demo's character, by the owner's choice): avatar character
  `kasia`, voice `omnivoice/kasia`, **English only**. Her idle still is
  `frontend/src/characters/kasia.webp`.
- **To change the character**, edit `character`, `name` and each language's `voice` in `persona.json`, and
  add the still as `frontend/src/characters/<character>.webp`. Nothing else names her. `roles` is the widget's
  label per tab.
- **One language, no toggle.** With one language the app shows no language toggle and the brain has no
  language switch. **To add a language**, add it under `languages` (label, name, voice, greetings, switch
  line), add its tag to `scene.json`'s `languages`, and give the brain its written lines (the say-soon lines
  in `backend/brain.py`). The voice must speak that language (`https://app.voqalize.com/api/v1/catalog.get`).

## Speech

Dollar amounts ("$18.50") and times ("7:30 PM") reach the voice as written. Room numbers are rewritten the
way a front desk says them ("room fourteen twelve"), as the speech streams (`backend/spoken.py`).

## Run it

```sh
cd demos/belmonte/frontend
pnpm install --ignore-workspace
cp .env.example .env    # VITE_AGENT_ID and VITE_PUBLISHABLE_KEY, to talk; without them it works by tap
pnpm dev --port 5470
```

Tests, from `demos/`:

```sh
uv run pytest tests/test_belmonte_e2e.py tests/test_demo_voice_contract.py -q
cd belmonte/frontend && pnpm typecheck && pnpm test && pnpm build
node scripts/screenshots.mjs <outDir>   # with the dev server on 5470
```

Data changes: edit `data/build_data.py`, then from `demos/`:
`uv run python belmonte/data/build_data.py` and
`uv run python -c "import sys; sys.path.insert(0, '.'); from belmonte.backend import hotel; hotel.write_cases()"`.
