# Varenya University — course advisor and admissions counsellor

A fictional large private university in India (Pune and Bengaluru campuses, plus Varenya Online)
with seven schools and 54 programmes: engineering, business, design, law, health sciences, liberal
arts, and online and executive education, at undergraduate, postgraduate, diploma and certificate
level. One voice agent talks to the visitor, often a student calling with their parents, in English
or Hindi, and moves the site while it talks. Everything (the university, its people, fees, dates and
outcomes) is invented.

## Landing pages and the agent's jobs

| landing | job | on screen |
| --- | --- | --- |
| `/programs` (and `/programs/<id>`, `/schools…`, `/`) | **Course advisor** | leads the learner from a broad wish to one programme: a level alone ticks it and gets the areas to choose from, an area alone lists every programme in it and asks which branch, anything more specific marks two or three picks; then the comparison, a programme's page opened at the part asked about (curriculum, fees, outcomes), the scholarship check and the application. Every reply ends on the next step |
| `/admissions`, `/apply` (and `/scholarships`, `/campus-life`) | **Admissions counsellor** | answers fees, eligibility, deadlines, scholarships, hostel and loan questions from the authored content, scrolling to each section; walks the family through the five-step application (personal, academics, programme, documents, fee), which fills in as they talk. The applicant presses Pay themselves |

The job follows the page: when the visitor moves from the finder to `/apply`, the same call becomes
the counsellor. `CONTRACT.md` is the UI ↔ brain contract: the Stage moves, the state events and the
data.

A dropped brain socket does not end the call: where Voqalize offers redial, the brain turns it on
and a redial within two minutes picks the call up where it was, in the same language and job, with
no second greeting (`backend/rejoin.py`; `CONTRACT.md`, Redial).

## Layout

- `persona.json`: the character (avatar, name, voice per language, languages, default language).
- `data/`: `catalogue.json` (schools, programmes, intakes, scholarships), `admissions.json`,
  `application.json` (the form as data), `campus_life.json`. Brain and page read the same files;
  the agent states only what they say.
- `backend/`: `brain.py` (`UniversityBrain`, an `OpenAIBrain` at `reasoning="medium"`),
  `finder.py` (matching, comparison, eligibility and scholarship rules), `prompt.py`,
  `data.py`, `rejoin.py` (live calls by session id, for a redial), `stage_gen.py` (generated),
  `routes.py`.
- `frontend/`: the Vite + React site, Stage performers in `src/stage/` (`view.ts` brings every
  highlighted target's whole group into view first, inner scroll areas included), the agent widget in
  `src/voice/`.

## The agent widget

One entry point on every page, the same widget as Paynora's. Idle, a bar at the bottom right holds
the character's still photo, the name, the job on this page (persona.json `roles`: course advisor or
admissions counsellor), EN / हिंदी and the call button. In a call the bar goes away and the face
becomes a draggable tile with the live avatar (it loads only then), the language toggle, mute,
minimise and end. No transcript is shown. The tile starts bottom right and steps aside for the page's
main actions (`data-dock-avoid`: Continue, Pay, the compare bar); the comparison dialog and the
filters drawer push it (or the idle bar) to the top right corner. The language is remembered in this
browser, so a reload keeps it and the next call starts in it.

## Run it

```sh
cd demos/university/frontend
pnpm install --ignore-workspace
pnpm exec vite --port 5407          # http://localhost:5407/demos/university/
```

The site works fully by click without a call. With `?debug=1` a console runs any Stage move by hand.
For a live call, copy `.env.example` to `.env` and set `VITE_AGENT_ID` and `VITE_PUBLISHABLE_KEY`
for an agent whose brain URL points at `wss://<brains host>/university`.

Tests: `cd demos && uv run pytest tests/test_university_e2e.py`. After editing the Stage spec,
regenerate from `demos/`:

```sh
uv run voqalize stage gen university/frontend/src/stage/scene.json --py university/backend/stage_gen.py --ts university/frontend/src/stage/scene.gen.ts
```

## Change the character or add a language

Edit `persona.json` and nothing else:

- **Character**: `character` (the `@voqalize/avatar` face; it also picks the idle bar's still photo,
  `frontend/src/characters/<character>.webp`, so add that file for a new character), `name`, `gender`
  (picks the Hindi first-person forms in the prompt), `role`, `roles` (the bar's label per job), and
  `voices` (one voice id per language; the voice must
  speak that language, as the speech tier's `/voices.json` lists). Then update the voice/language
  row for `university` in `demos/tests/test_demo_voice_contract.py`.
- **Language**: add it to `languages`, `voices`, `language_labels` and `language_names`. The page's
  toggle shows it at once; the brain also needs a greeting and a switch confirmation in that language
  (`backend/prompt.py` `greeting`, `backend/brain.py` `SWITCHED`) and, if it is not English or Hindi,
  a widening of the `Lang` type.
