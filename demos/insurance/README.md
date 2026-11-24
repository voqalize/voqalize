# Chhatri Insurance — a voice guide for a (fictional) Indian insurer

Chhatri Insurance (छतरी, "umbrella") sells car, two-wheeler, health, term life, home and travel
insurance. The site has a public side and a signed-in policyholder area for one sample customer,
Rohan Kulkarni of Pune, who holds six policies. A voice agent (today: **Ananya**, in English and
Hindi) talks with the customer and drives the screen with Stage while she talks.

Everything is invented: the company, the products, the premiums (`data/products.json`), the
policy wording (`data/policies/`), the customer, the garages and hospitals. Ananya states only
what those files say.

## Landing pages and the agent's jobs

The page the call starts on decides the job; the brain follows the visitor when they move.

| Landing | Job | What happens on screen |
| --- | --- | --- |
| `/quote`, `/quote/<product>`, `/insurance/<product>` | **Quote helper** | "I have a 2022 diesel SUV in Pune, about 14.5 lakh, two claim-free years" fills the quote form field by field; the premium builds with a transparent breakdown (own damage, NCB, third-party, add-ons, discounts, GST) computed from the rating tables. Add-ons switch on and off by voice or click. |
| `/my-policies`, `/my-policies/<policy>` | **Policy advisor** | "Am I covered if my engine is damaged in a flooded street?" opens the customer's actual policy document and marks the clause that answers it, with a verdict chip; she says plainly what is and is not covered, naming the clause. |
| `/claim` | **Claims assistant** | A long multi-section claim form (policy, what happened, driver, other party, police report, garage or hospital, treatment, bank, documents, review) fills in from what the customer says. She leads it one question at a time: each answer is filled the moment it is given and confirmed in a few words, then the next question; nothing she has is asked again. With every field filled she rings the uploads still owed, and opens the review once they are in. Uploads (mock) and Submit are the customer's. Motor and health claims. |
| `/` | Home | Asks which of the three they want and takes them there. |

## How it is built

- `backend/brain.py` — `InsuranceBrain`, an `OpenAIBrain` (`reasoning="medium"`). Tools:
  `update_quote`, `search_policy`, `mark_clause`, `open_policy`, `start_claim`, `fill_claim`,
  `review_claim`, `show_claim_section`, `go_to`, `set_language`. Every screen change is a Stage move
  sent with `stage.send`.
- `backend/rating.py` — the premium engine (the page has the same one in TypeScript;
  `data/quote_cases.json` holds golden cases both test suites check).
- `backend/claims.py`, `backend/policies.py`, `backend/quotes.py` — the claim form's rules, the
  clause search, and turning speech into form values.
- `backend/claim_lines.py` — her question for each claim field and the lines a claim turn ends on, per
  language. A claim tool's result carries the next question; if the model says nothing after it, the
  brain says that line itself (`owe` in `brain.py`), so a claim turn never ends in silence.
- `backend/amounts.py` — Indian amounts both ways: whatever the recognizer wrote ("around 1 and half
  lakhs", "one lakh fifty thousand", "15k", "dedh lakh", "डेढ़ लाख") read into rupees, and every written
  amount the voice is given turned into words ("one lakh fifty thousand rupees", "डेढ़ लाख रुपये"). The
  screen keeps ₹1,50,000.
- `frontend/src/stage/scene.json` — the Stage Spec: every move the agent can make and every state
  event the page sends. Regenerate after editing it:
  `cd demos && uv run voqalize stage gen insurance/frontend/src/stage/scene.json --py insurance/backend/stage_gen.py --ts insurance/frontend/src/stage/scene.gen.ts`
- `CONTRACT.md` — the agreement between the page and the brain.

## Redial

A dropped brain socket does not end the call. Where Voqalize offers redial, the brain turns it on, and
a redial reaching this process within two minutes picks the call up where it was: job, language,
quote, claim, the model's history and the screen, with no second greeting (`backend/rejoin.py`,
CONTRACT.md "Redial").

## Run it

```bash
# Brains (from demos/): every demo's brain, this one at /insurance
cd demos && uv run uvicorn voqalize_demos.umbrella:app --reload --port 8080

# The UI
cd demos/insurance/frontend
cp .env.example .env            # VITE_AGENT_ID / VITE_PUBLISHABLE_KEY, once provisioned
pnpm install --ignore-workspace
pnpm dev --port 5405            # http://localhost:5405/demos/insurance/
```

Without an agent configured the whole site works by click, and the dock's call button is off.
`?debug=1` opens a console that fires any Stage move by hand, and its "Fake call" shows the call tile.

## The agent widget

One entry point, the same as Paynora's: no transcript anywhere.

- **Idle:** a bar at the bottom right (full width on a phone) with Ananya's still photo, her name,
  the job on this page (`roles` in `persona.json`: Insurance guide, Quote guide, Policy explainer,
  Claim helper, by the brain's own page-to-job rule), the EN / हिंदी toggle and "Talk to Ananya".
  It moves to the left, or steps aside, when a primary action (`data-dock-avoid`) is under it.
- **In a call:** the bar goes away and a draggable face tile holds the live avatar (the avatar
  runtime starts only here), the language toggle, mute, minimise and end. It starts bottom right on
  a desktop and top right on a phone, never over Continue, Submit claim or Continue to buy, and
  moves clear of anything open over the page (`data-overlay`: the phone menu).
- **Language** is remembered in this browser (`chhatri-lang`); the next call and a redial start in it.
- **Highlights are shown whole (X1):** every Stage scroll goes through `frontend/src/stage/view.ts`,
  which brings the target's group (`data-stage-group`: the add-ons, the claim types, the documents
  owed, a policy section) fully into view, inner scroll areas first, under the sticky header.

Tests: `cd demos && uv run pytest tests/test_insurance_e2e.py` (the brain over the real wire,
scripted model) and `cd demos/insurance/frontend && pnpm test`.

## Change the character or add a language

The character lives in **one file, `persona.json`**: avatar character id, display name (and its
Devanagari spelling), gender, the dock's label per job (`roles`), the languages offered with the voice and both speech legs for each,
and the default language. The page (`frontend/src/persona.ts`) and the brain
(`backend/persona.py`) both read it.

- **Another character:** change `character`, `name`, `names`, `gender` and each language's
  `voice` in `persona.json`, and add the still photo the idle dock shows at
  `frontend/src/characters/<character>.webp` (without one the dock shows the initial). The greetings in `backend/persona.py` (`GREETINGS`) are written
  sentences: the Hindi ones use feminine verb forms (सकती, भरती), so a male character needs those
  four Hindi lines adjusted too.
- **Another language:** add a row to `languages` in `persona.json` (code, label, voice, `stt`, `tts`
  — check the voice speaks it in the voice catalogue first), then add that language to each entry
  of `GREETINGS` and to `SWITCHED` in `backend/persona.py`. The brain refuses to start if a language
  has no greeting.
