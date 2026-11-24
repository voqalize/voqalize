# Varenya University — UI ↔ brain contract (v1)

Varenya University is a fictional large private university in India (Pune and Bengaluru campuses plus
Varenya Online) and a Voqalize voice demo. One agent, whose character lives in `persona.json`, does two
jobs, chosen by the page the call is on:

| landing | job | what it does on screen |
| --- | --- | --- |
| `/programs`, `/programs/<id>`, `/schools…`, `/` | **course advisor** | hears goal, level, interests, budget and hours a week; ticks the programme finder's filters as it talks; marks two or three picks; opens the side-by-side comparison; opens programme pages |
| `/admissions`, `/apply`, `/scholarships`, `/campus-life` | **admissions counsellor** | answers fees, eligibility, deadlines, scholarships, hostel and loans from the authored content; fills the five-step application with the family as they talk |

The brain follows the visitor: a route change (Stage `hello`) switches the job.

This file is the agreement between `frontend/` and `backend/`. Change it only in the same PR as the code.

## Persona and languages

`persona.json` is the only place the character lives: avatar `character`, display `name`, `gender`
(Hindi first-person forms), `voices` per language, `languages`, `default_language`, toggle labels.
The page imports it (dock copy "Talk to {name}", avatar, the still photo
`frontend/src/characters/<character>.webp`, the dock's role label per job from `roles`, alt text, the
EN / हिंदी toggle); the brain
imports it (voice per language, greetings, prompt). Nothing else names the character.

The visitor picks the language before the call (toggle by the call button); it rides `init.lang`
(`"en"` | `"hi"`). The brain configures both legs in `on_session_start`. Mid-call the toggle sends the
app event `language_requested{language}`; the brain also switches when it hears Hindi or is asked, and
tells the page with the action `language_changed{language}` so the toggle follows. The page remembers
the last language used (localStorage `varenya-lang`), so after a reload the toggle and the next
call's `init.lang` start in it.

## Data (single source of truth, read by both halves)

- `data/catalogue.json` — university, 7 schools, campuses, levels, modes, fee bands, hour bands,
  intakes (with round deadlines), 8 scholarships, 54 programmes. A programme: `id, name, award, school,
  level (ug|pg|diploma|certificate), mode (full_time|online|weekend|hybrid), campuses[], duration_months,
  duration_label, hours_per_week, fee_per_year, fee_total, application_fee, seats, intake, eligibility{
  requires, min_percent, needs, streams[], min_experience_years?}, entrance[], selection[], scholarships[],
  outcomes{placement_pct?, median_ctc_lpa?, highest_ctc_lpa?, note?, roles[]}, highlights[], modules[],
  interests[], specialisations[]`.
- `data/admissions.json` — process, VUSAT, fees (one-time, seat confirmation, instalments, zero-interest
  plan, refund, payment methods), hostel (rooms per campus), loans, scholarship rules, documents, FAQs,
  contact.
- `data/application.json` — the application form as data: 5 steps, each field's `name`, `label`, `type`
  (`text | percent | choice | program | intake | scholarship | document`), `required`, `options`
  (`[id, label]`). Document fields take `uploaded` | `later`.
- `data/campus_life.json` — campus-life sections.

**No invented facts.** UI and speech state only what these files say. Money as ₹ with Indian grouping
(₹3,40,000), dates DD MMM YYYY.

## Finder facets (the filter labels both halves use)

| facet | options (label → catalogue match) |
| --- | --- |
| `Level` | Undergraduate, Postgraduate, Diploma, Certificate (`levels`) |
| `School` | each school's `short` (Engineering, Business, Design, Law, Health Sciences, Liberal Arts, Online & Executive) |
| `Mode` | Full-time on campus, Online, Weekend, Hybrid (`modes`) |
| `Campus` | Pune, Bengaluru, Online (`campuses[].name`) |
| `Fee` | `fee_bands[].label`, matched on `fee_per_year` |
| `Hours` | `hour_bands[].label`, matched on `hours_per_week` |

Within a facet, ticked options OR; across facets, AND. Sorted by fee per year, ascending, by default.

## Stage moves (scene: `frontend/src/stage/scene.json`)

Generated with, from `demos/`:
`uv run voqalize stage gen university/frontend/src/stage/scene.json --py university/backend/stage_gen.py --ts university/frontend/src/stage/scene.gen.ts`

| move | verb | class | args | performer |
| --- | --- | --- | --- | --- |
| `catalogue.filter` | filter | reversible | `facet, value` | on `/programs` (navigates there first if needed): rings the sidebar option `data-stage-part="<Facet>:<Option>"`, beat, ticks it; returns "Level: Postgraduate ticked, 9 programmes". Refuses with the facet's options. |
| `catalogue.clear` | clear | reversible | `facet?` | unticks a facet or all. |
| `catalogue.pick` | pick | reversible | `first, second?, third?` (programme ids) | rings each card in turn (navigating to `/programs` if needed; a pick hidden by filters is still shown, pinned at the top), badges 1..3, shortlist tray. |
| `catalogue.compare` | compare | look | `first, second, third?` | opens the comparison panel (rows below), rings it. |
| `site.open` | open | navigate | `program` | navigates to `/programs/<id>`, rings the title. |
| `site.go` | go | navigate | `page` | `home, programs, admissions, scholarships, campus-life, apply, schools, schools/<id>`. |
| `site.show` | show | look | `target` | scrolls to and rings `[data-stage-thing="<target>"]` on the page in front; refuses with the names on the page. |
| `apply.fill` | fill | reversible | `field, value` | on `/apply` (navigates there first): opens the field's step, rings the input, sets it. Validates against `application.json` (choice ids or labels; percent 0–100; `program` a catalogue id; `campus` one of the programme's campuses; `intake` the programme's intake label; `scholarship` one of the programme's scholarship ids or `none`; documents `uploaded|later`). |
| `apply.step` | step | look | `step` 1..5 | opens and rings that step. |
| `apply.next` | next | reversible | — | as Continue: refuses naming required fields still empty. |

Paying is never a move: the applicant presses **Pay ₹<fee> and submit** themselves. The page then shows
the application number `VRN-27-<5 digits>` and stores the application in localStorage.

Comparison rows: Duration, Mode, Campus, Fee per year, Total fee, Hours a week, Eligibility, Selection,
Next deadline, Scholarships, Placement / outcome, Median salary.

## Slices and events (page → brain, `stage_event`)

- `catalogue.changed` (set): `filters[]` ("Level: Postgraduate"), `count`, `top[]` (first 6 ids
  listed), `picks[]`, `compared[]`.
- `application.changed` (merge): `field`, `filled[]`, `missing[]` (required fields of the step in front),
  `step`, and the non-personal values `program, campus, intake, class12_stream, class12_percent,
  graduation_percent, entrance_exam, hostel, room_type, scholarship`. Names, date of birth, mobile,
  email and parent's name are never sent: only that they are filled.
- `application.step_reached` (merge): `step`.
- `application.submitted` (merge, react speak): `reference`.

The page sends `by: "agent"` for changes made inside a move (Stage's `AGENT_WINDOW_MS`), otherwise
`by: "visitor"`.

## App events and actions beside Stage

- UI → brain `language_requested{language: "en"|"hi"}` — the visitor pressed the toggle mid-call.
- Brain → UI `language_changed{language: "en"|"hi"}` — the call's language moved; the toggle follows.

## Redial: a call outlives a dropped brain socket (owner, 2026-11-23)

On a voice runtime that offers redial (`session.can_redial`, SDK 0.15.0 `Config.redial`),
`on_session_start` turns it on with both legs. Each live brain is kept in this process by session id
(`backend/rejoin.py`) while its socket is up and for two minutes after it drops. A redial that reaches
the same process adopts the call as it was: the page, the job, the language (both legs configured in
it again, whatever `init.lang` says), the model's history, the Stage director with its screen mirror
(finder and application) and pending cues, a language-switch line not yet said and a reaction left
for the next quiet spell. The call-start note is not added again, and the greeting a redialled brain
returns (not spoken by Voqalize) is kept out of the model's history. A redial that reaches a fresh
process, or comes after the two minutes, starts as a new conversation on the same page. Nothing here
changes the page: its state never left the browser. `Config.late` stays at Voqalize's default.

## Frontend rule

Everything works by click alone. Every performer calls the same zustand store actions the page's
own controls call. A dev-only console (`?debug=1`) runs any move by hand through the same `Moves`
instance the call uses.
