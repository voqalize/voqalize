# Dantika Dental: the front desk

A fictional two-branch dental clinic in Bengaluru (Indiranagar and HSR Layout) and a Voqalize
voice demo. Meera, the front desk, books appointments, procedures and scans on each dentist's
real calendar, moves and cancels them under the clinic's policy, answers visit questions from
the clinic's own instructions, and sends anything clinical to a dentist as a callback. She speaks
English or Hindi, and she drives the screen with Stage while she talks: every slot, summary,
sign-in step and change sheet she talks about is rung on the page before it changes.

Everything also works by click alone. The page and the brain read the same data, so the slots
she offers are the ones the calendar shows.

## Landing pages

| route | what the front desk does there |
| --- | --- |
| `/demos/dental/` | the clinic site: services and prices, dentists, branches, parking, visit information. She answers from the authored instructions and starts a booking |
| `/demos/dental/book` | booking: service, branch and dentist, the calendar (day or week, per dentist or imaging room), the slot, the patient's phone and code, the summary and Confirm |
| `/demos/dental/my-appointments` | sign in with phone and code; reschedule or cancel with a change sheet that shows the policy and fee, confirmed by a spoken yes |

The call starts on whichever page the visitor is on, and that page sets her job; she follows
the visitor to the others.

## The agent widget

One entry point on every page, the same widget as Paynora's. Idle, a bar at the bottom right
with Meera's still photo, her name, the job on this page (persona.json `roles`), EN / हिंदी and
"Talk to Meera". In a call the bar goes away and a draggable face tile holds the live avatar
(only there does the avatar runtime start), the language toggle (mid-call it asks her to
switch), mute, minimise and end. No transcript is shown anywhere. The language is remembered in
the browser across reloads, so the next call and a redial start in it. The bar and the tile step
aside for the page's main buttons (`data-dock-avoid`: Book an emergency visit, Confirm, the
sign-in buttons, a change sheet's Confirm and Keep), and move to a top corner under the header
when the callback card covers their place on a phone (`data-overlay`). Whatever she rings is
first scrolled fully into view with the group around it (`frontend/src/stage/view.ts`).

## What is real here

- **Slots are computed** (`backend/clinic.py`, and `frontend/src/data/slots.ts` by the same
  algorithm in `CONTRACT.md`): dentist schedules and breaks, chairs by kind (general, surgical,
  aesthetic), imaging rooms, other patients' bookings (`data/bookings.json`), lead time and the
  21-day window. `data/slot_fixtures.json` holds the two engines to the same answers.
- **Rules**: a CBCT needs a referral or a consultation first; wisdom-tooth surgery needs an OPG
  from the last six months; a root canal is three sittings, 7 to 14 days apart, with the later
  two pencilled in when the first is booked.
- **Policy**: free changes up to 24 hours before, then a ₹300 late fee (waived for emergencies),
  scans free up to 2 hours before, two online changes per appointment.
- **Clinical questions** (bleeding, swelling, fever, medicines) are never answered: she offers a
  dentist's callback, with the authored red-flag line first when it applies.
- **Sample patients** (demo OTP `4821`): Rohan Mehta `98450 31726` (root canal in progress,
  a cleaning), Ishita Banerjee `99000 48213` (aligner consult; no referral, so no CBCT),
  Suresh Gowda `98860 55102` (check-up on the next open day, an OPG, a CBCT referral on file).
  Any other mobile number is a new patient.
- **Redial**: if the brain's socket drops mid-call (a restart, a network blip), Voqalize dials
  it again and the call carries on where it was, with no second greeting: language, page,
  patient, held slot, pending change, the call's calendar and the model's history are kept in
  memory by session id for two minutes (`backend/rejoin.py`, `CONTRACT.md` "Redial").

Dates are never stored: bookings name a week relative to the current one and a weekday, so the
calendar is full whatever day the demo runs.

## Files

- `persona.json`: the character (avatar, names, voices, languages). See below.
- `data/clinic.json`: the clinic, branches, dentists, services, rules, policy, instructions,
  sample patients. `data/bookings.json`: everyone else's appointments, from
  `data/build_bookings.py` (fixed seed).
- `CONTRACT.md`: the page ↔ brain agreement: the slot algorithm, the Stage moves, the events.
- `frontend/src/stage/scene.json`: the Stage Spec. `backend/stage_gen.py` and
  `frontend/src/stage/scene.gen.ts` are generated from it.
- `backend/brain.py` (an `OpenAIBrain`), `backend/clinic.py` (data and calendar),
  `backend/prompt.py` (instructions, greetings, written lines), `backend/app_events.py` (page →
  brain events).
- `demos/tests/test_dental_e2e.py`: the e2e, one storyline per landing page.

## Run it

```bash
# Brain (every demo's, one process)
cd demos && uv run uvicorn voqalize_demos.umbrella:app --reload --port 8080

# The page
cd demos/dental/frontend
cp .env.example .env          # VITE_AGENT_ID / VITE_PUBLISHABLE_KEY, once provisioned
pnpm install --ignore-workspace
pnpm dev                      # /demos/dental/
```

Without an agent configured the site works fully by hand and the call button says voice is not
on. Add `?debug=1` for the console that runs any Stage move by hand.

Tests: `cd demos && uv run pytest tests/test_dental_e2e.py`, and in `frontend/`:
`pnpm typecheck && pnpm test && pnpm build`.

After editing data: `uv run python dental/data/build_bookings.py` (only when schedules or patient
appointments change) and `uv run python dental/backend/clinic.py` (the slot fixtures), from
`demos/`. After editing the Stage Spec: `uv run voqalize stage gen
dental/frontend/src/stage/scene.json --py dental/backend/stage_gen.py --ts
dental/frontend/src/stage/scene.gen.ts`. After editing `backend/app_events.py`: `uv run voqalize
types dental/backend/app_events.py -o dental/frontend/src/voice/events.gen.ts`.

## Change the character or add a language

Edit `persona.json` and nothing else for the character:

- `character`: the `@voqalize/avatar` face (a name from `listCharacters()`). It also names the
  still photo the idle bar shows, `frontend/src/characters/<character>.webp`: add one for a new
  character (without it the bar shows her initial).
- `roles`: the label under her name in the bar and the tile, per page.
- `names`: how she says her own name, per language (greetings and the call button read it).
- `voices`: a Voqalize voice id per language. The voice must speak that language (the speech
  tier's `/voices.json` lists each voice's languages); `omnivoice/meera` speaks `en` and `hi`.
- `languages` and `default_language`: what the toggle offers and what a call starts in.

A new language also needs its greetings and written lines in `backend/prompt.py` (`GREETINGS`,
`LINES`; a test fails if one is missing), and the `Lang` type in `backend/persona.py` and
`app_events.py` widened to the new code.
