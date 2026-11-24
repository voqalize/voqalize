# Paynora app (`payroll_app`)

The product of **Paynora**, a fictional Indian HR and payroll SaaS, signed in as Meghna Rao, HR admin
of **Banyan & Bay Foods Pvt. Ltd.** (a fictional customer, 56 employees in Bengaluru, Mumbai, Pune,
New Delhi and Hyderabad). A voice agent talks with the admin and drives the app on screen with
Stage: she opens screens, rings what she talks about, fills forms, and makes changes after a spoken
yes. Every company, person and number is invented. Its sibling `payroll_site` is Paynora's marketing
site.

The app works by click alone: dashboard, employees (list, detail, add), payroll runs (register, the
February 2026 draft and its approve flow), payslips (line by line, compared with the month before),
leave, reimbursements, tax (declarations and proofs, regime comparison slab by slab, Form 16),
settings, help, and an employee self-service view ("View as employee"). The demo's clock is frozen
at 16 Feb 2026, in FY 2025-26. Tax figures are illustrative, FY 2025-26.

## Landing pages and the agent's jobs

One brain (`backend/brain.py`), one job per landing page. The page sends the landing in `init`; the
brain also follows the admin as she moves (`screen.viewed`).

| Landing | Job | What she does |
|---|---|---|
| `/welcome` | Onboarding guide | Walks the setup wizard one step at a time. Company details come from signup; for the pay structure and the leave policy she asks what the admin wants or offers the common defaults (editable): the values the admin says go in directly, each field once, and the defaults only fill the fields she left out, only when she says so; the admin imports the employee file herself (an example of the columns and a downloadable sample, `data/employees_import.csv`, are on the step); then a February 2026 test payroll whose totals equal the draft run. |
| `/`, `/help` | In-app support | "Why is Ravi's net pay lower this month?" opens his January payslip beside December and explains each line from the data (2 days' loss of pay, TDS up after proofs for ELSS and NPS were not submitted, reimbursements). Approves or rejects leave (recomputing the draft when it becomes loss of pay), fixes or decides a claim, adds an employee (prorated February pay), opens any month's payroll run (who earned the most), and, only for something substantial she cannot do, offers a support or feature request, written out in a panel beside the screen and sent after a yes. |
| any other screen | Feature coach | "How do I switch to the old regime?" opens that screen and rings each control in turn; compares both regimes slab by slab from the engine; switches after a yes, recomputing February TDS. |

**Admin view and employee view.** "View as Aditi" switches to the employee self-service view, and
it stays: every request is answered from that employee's side with only what she can see ("show me
November's payslip" is her November payslip, in her view); admin work and other employees are
refused there until the admin says "switch to admin" or "view as" someone else, or leaves the view
herself.

Changes are never cues. A tool that changes something only asks; the admin's yes (English or Hindi)
is classified before the model runs, the brain sends the confirmed Stage move, and the page's answer
is said once (`backend/confirm.py`). Approving a payroll run pays people, so it is not a move: the
admin presses that button.

The contract between the page and the brain is `CONTRACT.md`; the moves are
`frontend/src/stage/scene.json`.

## Data and the engine

- `data/product.json` — brand, palette, type, logo, modules, plans and the FY 2025-26 tax rules.
  Hand-written; `payroll_site` keeps a byte copy.
- `data/company.json`, `data/employees_import.csv`, `data/tax_fixtures.json` — written by
  `data/build_data.py` from the engine. Regenerate from `demos/`:
  `uv run python payroll_app/data/build_data.py`.
- `backend/payroll_engine.py` — the salary structure, payslip (LOP, PF, ESI, PT, TDS spread over the
  months left) and income tax per regime with slab lines. The brain's session books
  (`backend/books.py`) start from a fresh copy of `company.json` and recompute with it.
- `frontend/src/lib/engine.ts` — its TypeScript twin, which the page's store uses for every
  recomputation. Both are held to the 107 cases in `data/tax_fixtures.json` by
  `frontend/src/lib/engine.test.ts` (vitest); the e2e test checks that `company.json`,
  `tax_fixtures.json` and the import file are exactly what `build_data.py` writes now. Change one
  engine, change both, regenerate, and run both tests.

## Run it

```sh
# the brain, with the other demos (from demos/)
uv run pytest tests/test_payroll_app_e2e.py tests/test_demo_voice_contract.py -q

# the page
cd payroll_app/frontend
pnpm install --ignore-workspace
pnpm dev --port 5403          # http://localhost:5403/demos/payroll_app/
pnpm typecheck && pnpm test && pnpm build
```

Without `VITE_AGENT_ID` and `VITE_PUBLISHABLE_KEY` (see `.env.example`) the app runs without a call.
Add `?debug=1` for the dev console, which fires any Stage move through the same performers the agent
uses.

## A dropped socket does not end the call

Where Voqalize offers redial, the brain turns it on. If its socket drops without a hang-up (a
restart, a network blip), Voqalize dials it again for the same session and the new brain picks up
the call from `backend/rejoin.py`: the session's own copy of the books with every change made so
far, the job, language, a change waiting for a yes and the model history, with no second greeting.
Calls are held in process memory for two minutes after the drop, so a redial that reaches a freshly
deployed process starts again from `company.json`. See `CONTRACT.md`, Redial.

## Change the character or add a language

The character lives in one file, `persona.json`: display name, avatar character, the voice for each
language, the languages offered (with their toggle labels) and the default. The brain reads it in
`backend/persona.py`, the page in `frontend/src/persona.ts`; prompts, greetings, "Talk to …", alt
text and tests all take it from there. To change the character, edit `persona.json` (pick an avatar
character and a voice that speaks every listed language; see the catalog at
`/api/v1/catalog.get`), set `hindi_forms` to the gender of the first-person forms the character
uses in Hindi, and add the character's still photo as `frontend/src/characters/<avatar_character>.webp`
(the idle dock shows it; the live avatar mounts only when a call is up). `roles` holds the dock's label per job (onboarding, support, coach), picked
by the page in front, as the brain picks the job.

To add a language: add it to `languages` and `voices` in `persona.json`, then give it a greeting per
job in `backend/prompt.py` (`GREETINGS`), its toggle line (`TOGGLE_CONFIRM`) and its held line
(`HELD` in `backend/brain.py`), and a form for every line the brain writes itself (`_t(...)` in
`backend/brain.py`, the outcome lines in `backend/confirm.py`: in a Hindi call every ask and outcome
is Hindi, with product words such as approve, payslip and regime kept as they are). The brain configures both legs (recognizer and voice) from
`persona.json` in `on_session_start`, and again when the toggle or the admin switches language
mid-call. The visitor's language is remembered in the browser (`frontend/src/savedLang.ts`), so a
reload keeps the toggle, and the next call, on the language last used.
