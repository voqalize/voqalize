# Anvaya University — course advisor and admissions counsellor

A fictional large private university in India (Pune and Bengaluru campuses, plus Anvaya Online)
with seven schools and 54 programmes: engineering, business, design, law, health sciences, liberal
arts, and online and executive education, at undergraduate, postgraduate, diploma and certificate
level. One voice agent talks to the visitor, often a student calling with their parents, in English
or Hindi, and moves the site while it talks. Everything (the university, its people, fees, dates and
outcomes) is invented.

## Landing pages and the agent's jobs

| landing | job | on screen |
| --- | --- | --- |
| `/programs` (and `/programs/<id>`, `/schools…`, `/`) | **Course advisor** | hears the learner's goal, current level, interests, budget and hours a week; the programme finder's filters tick as it talks; it marks two or three picks, explains each fit and opens the side-by-side comparison |
| `/admissions`, `/apply` (and `/scholarships`, `/campus-life`) | **Admissions counsellor** | answers fees, eligibility, deadlines, scholarships, hostel and loan questions from the authored content, scrolling to each section; walks the family through the five-step application (personal, academics, programme, documents, fee), which fills in as they talk. The applicant presses Pay themselves |

The job follows the page: when the visitor moves from the finder to `/apply`, the same call becomes
the counsellor. `CONTRACT.md` is the UI ↔ brain contract: the Stage moves, the state events and the
data.

## Layout

- `persona.json`: the character (avatar, name, voice per language, languages, default language).
- `data/`: `catalogue.json` (schools, programmes, intakes, scholarships), `admissions.json`,
  `application.json` (the form as data), `campus_life.json`. Brain and page read the same files;
  the agent states only what they say.
- `backend/`: `brain.py` (`UniversityBrain`, an `OpenAIBrain` at `reasoning="medium"`),
  `finder.py` (matching, comparison, eligibility and scholarship rules), `prompt.py`,
  `data.py`, `stage_gen.py` (generated), `routes.py`.
- `frontend/`: the Vite + React site, Stage performers in `src/stage/`, the voice dock in
  `src/voice/`.

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

- **Character**: `character` (the `@voqalize/avatar` face), `name`, `gender` (picks the Hindi
  first-person forms in the prompt), `role`, and `voices` (one voice id per language; the voice must
  speak that language, as the speech tier's `/voices.json` lists). Then update the voice/language
  row for `university` in `demos/tests/test_demo_voice_contract.py`.
- **Language**: add it to `languages`, `voices`, `language_labels` and `language_names`. The page's
  toggle shows it at once; the brain also needs a greeting and a switch confirmation in that language
  (`backend/prompt.py` `greeting`, `backend/brain.py` `SWITCHED`) and, if it is not English or Hindi,
  a widening of the `Lang` type.
