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
| `/claim` | **Claims assistant** | A long multi-section claim form (policy, what happened, driver, other party, police report, garage or hospital, treatment, bank, documents, review) fills in from what the customer says; she asks only for what is missing and takes them to the review step. Uploads (mock) and Submit are the customer's. Motor and health claims. |
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
- `frontend/src/stage/scene.json` — the Stage Spec: every move the agent can make and every state
  event the page sends. Regenerate after editing it:
  `cd demos && uv run voqalize stage gen insurance/frontend/src/stage/scene.json --py insurance/backend/stage_gen.py --ts insurance/frontend/src/stage/scene.gen.ts`
- `CONTRACT.md` — the agreement between the page and the brain.

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

Without an agent configured the whole site works by click, and the dock says voice is coming.
`?debug=1` opens a console that fires any Stage move by hand.

Tests: `cd demos && uv run pytest tests/test_insurance_e2e.py` (the brain over the real wire,
scripted model) and `cd demos/insurance/frontend && pnpm test`.

## Change the character or add a language

The character lives in **one file, `persona.json`**: avatar character id, display name (and its
Devanagari spelling), gender, the languages offered with the voice and both speech legs for each,
and the default language. The page (`frontend/src/persona.ts`) and the brain
(`backend/persona.py`) both read it.

- **Another character:** change `character`, `name`, `names`, `gender` and each language's
  `voice` in `persona.json`. The greetings in `backend/persona.py` (`GREETINGS`) are written
  sentences: the Hindi ones use feminine verb forms (सकती, भरती), so a male character needs those
  four Hindi lines adjusted too.
- **Another language:** add a row to `languages` in `persona.json` (code, label, voice, `stt`, `tts`
  — check the voice speaks it in the voice catalogue first), then add that language to each entry
  of `GREETINGS` and to `SWITCHED` in `backend/persona.py`. The brain refuses to start if a language
  has no greeting.
