# Dantika Dental — page ↔ brain contract (v2)

Dantika Dental Studio is a fictional two-branch dental clinic in Bengaluru (Indiranagar and HSR
Layout) and a Voqalize voice demo. The front-desk agent (character, voices and languages in
`persona.json`; never written anywhere else) books, moves and cancels appointments, procedures and
scans on each dentist's real calendar, answers visit questions from the clinic's own instructions,
and sends anything clinical to a dentist as a callback. She drives the screen through **Stage**.

This file is the agreement between `frontend/` (React, Vite) and `backend/` (the brain). Change it
only in the same PR as the code.

## Data (read by both sides; nothing else is a source of facts)

- `persona.json` — avatar `character` (also the still photo `frontend/src/characters/<character>.webp`),
  `names` per language, `roles` per page (the widget's label), `voices` per language, `languages`
  offered (code, label, short), `default_language`.
- `data/clinic.json` — clinic, branches (chairs, imaging rooms, parking), dentists (weekly
  schedules), services (category, duration, price range, eligible dentists, chair kinds, imaging
  resource, sittings, `requires`), rules, cancellation policy, visit instructions, clinical topics,
  sample patients and their upcoming appointments, the demo OTP.
- `data/bookings.json` — other patients' appointments (generated once by
  `data/build_bookings.py`, fixed seed). Shown as "Booked", never with a name.
- `data/slot_fixtures.json` — written by `backend/clinic.py` (`write_fixtures`): slots for a fixed
  "now". The page's slot engine has a test that must reproduce it exactly.

### Dates

Nothing stores a date. A booking has `week` (relative to the current week; 0 = this week, weeks
start Monday) and `day` (`mon`…`sun`): date = Monday of today's week + 7·week + index(day). A
booking with `"anchor": "next_open_day"` is on the first day after today that is not a Sunday.
"Today" and "now" are in **Asia/Kolkata**, always (compute with `Intl` / `toLocaleString` and
`timeZone: "Asia/Kolkata"`, never the browser's zone).

### Slots (both engines, exactly this)

For service `s`, date `d`, optional branch `b`, optional dentist `x`, optionally ignoring one
appointment id (when moving it):

1. No slots unless `today ≤ d ≤ today + booking.horizon_days`.
2. `earliest` = 0 on a later day; on today, minutes-now + `emergency_lead_min` if `s.same_day`
   else + `lead_min`.
3. Step = `booking.slot_step_min` (15). Duration = `s.duration_min`.
4. **Imaging** (`s.resource` set): for each branch (filtered by `b`) open on `d`'s weekday, each
   imaging room whose `does` contains `s.resource`, each room session: for `t` = session start,
   +step, while `t + dur ≤ session end`: a slot when `t ≥ earliest` and no live appointment holding
   that room overlaps `[t, t+dur)`.
5. **Dentist services**: for each dentist id in `s.dentists` (in that order; filtered by `x`), each
   of their sessions on that weekday (filtered by `b`): same stepping; a slot when `t ≥ earliest`,
   the dentist has no overlapping live appointment, and at least one chair of that branch, in the
   branch's chair order, whose `kind` is in `s.chairs`, has no overlapping live appointment — the
   slot takes the **first** such chair.
6. An appointment "holds" its dentist, chair and resource ids. Overlap: `a.start < end && start < a.end`.
   Live = status `booked` (cancelled ones free their time).
7. Output sorted by start time, then by dentist id (or room id).

**Root canal sittings** (`sittings: 3`, `sitting_gap_days {min:7,max:14}`): after the first slot,
each next sitting is on the first day `k` in `min..max` days after the previous sitting that has any
slot with the same dentist (excluding times within one duration of a sitting already planned that
day); on that day pick the slot nearest the first sitting's start time, preferring the first
sitting's branch on a tie.

**Rules** (`requires`): `cbct_referral` — a CBCT needs the patient's referral `for: "cbct"`, or a
visit (history or booked) with a service in the rule's `consult_services` on or before the scan
date. `opg_recent` — wisdom-tooth surgery needs an OPG (history or booked) in the 180 days up to the
surgery date. Unknown patient → the rule is told, not decided.

**Cancellation / reschedule terms**: past or started → not allowed; `changes ≥ online_changes_max`
→ not online (callback); imaging: free ≥ 2 h before, else the late fee; otherwise free ≥ 24 h
before; within 24 h a ₹300 late fee, waived for `emergency`. A root canal's sitting n>1 may only move
to 7–14 days after sitting n−1.

## Pages (landing routes; base `/demos/dental/`)

| route | the agent's job there (the brain's mode) |
| --- | --- |
| `/` | the clinic site: services and prices, dentists, branches and hours, visit information; answers questions, starts a booking |
| `/book` | booking: service → branch & dentist → calendar & slot → patient (phone + OTP, typed by the patient) → confirm; the dentist/room calendar (day/week) updates live |
| `/my-appointments` | sign in with phone + OTP, typed by the patient; upcoming appointments with Reschedule / Cancel (a confirm sheet with the policy line and fee); visit instructions per appointment |

The call starts with `init = {surface: "dental-web", landing, path, lang, patient_id}` where
`landing` is `home | book | my-appointments`, `lang` is the toggle's code (`en`/`hi`) and
`patient_id` names the patient already signed in on this browser (or `null`); never a number. Every page works by
click alone; the call button (with the EN / हिंदी toggle beside it) is on every page.

## Brain → page: Stage moves (`frontend/src/stage/scene.json`)

Generated with `uv run voqalize stage gen dental/frontend/src/stage/scene.json --py
dental/backend/stage_gen.py --ts dental/frontend/src/stage/scene.gen.ts` (from `demos/`). Every
performer rings what it touches before it changes anything, refuses with what the page offers
instead of guessing, writes through the same store controller the clicks use (with `by: "agent"`),
and returns one short line.

| move | class | what the page does |
| --- | --- | --- |
| `site.go {page}` | navigate | rings the header link, routes there |
| `site.show {thing}` | look | scrolls to and rings `[data-stage-thing=thing]`; opens home first if only home has it |
| `book.slots {service_id, date, branch_id?, dentist_id?, view}` | reversible | opens /book, selects the service, branch, dentist (or the imaging room), sets the calendar to that day/week, rings the free slots |
| `book.hold {service_id, branch_id, date, time, dentist_id?, chair_id?, resource_id?, sittings?}` | reversible | selects the slot, rings it, shows the summary card (price range, duration, prep line, later sittings) with Confirm. Refuses a slot that is not free |
| `book.confirm {booking_id, patient_id, …same…, sitting_ids?}` | confirmed | writes the appointment(s) with these ids to the store, shows the confirmation; the calendar block turns "Your appointment" and pulses |
| `patient.ask {field?}` | look | opens the sign-in panel (booking page when a slot is held, else My appointments) and rings the box the patient types in next (`phone`, `code` or `name`; none for the current step). Fills nothing |
| `patient.name {name}` | reversible | registers the new patient (`P-` + 4 digits, minted by the page); detail names the id |
| `appt.focus {appointment_id}` | look | rings that appointment's card |
| `appt.propose {appointment_id, action, fee, date?, time?, branch_id?, dentist_id?, chair_id?, resource_id?}` | reversible | opens the change sheet on the card: old → new (or the cancellation), the policy line, the fee, Confirm / Keep |
| `appt.apply {…same…}` | confirmed | makes the change; the card and the calendar update |
| `callback.request {callback_id, reason, urgency, window}` | reversible | shows the callback card (reference, what about, when); the dentist calls the signed-in patient's number on record. Refuses when nobody is signed in |
| `cal.view {date, dentist_id?, resource_id?, mode}` | look | puts that calendar on screen and rings it |

Plus one plain action outside Stage: `language_changed {language}` moves the EN / हिंदी toggle.

## Page → brain events (`backend/app_events.py`; TS in `frontend/src/voice/events.gen.ts`)

`page_viewed{page, path}`, `schedule_changed{appointments[]}` (every appointment this browser made
or changed, whole, with its real date; on connect and after every change), `patient_signed_in
{patient_id, name, first_name, is_new, restored}` (`restored`: signed in before the call, sent on
connect), `sign_in_step{step}` (`code_sent | bad_phone | wrong_code | name_needed`),
`patient_signed_out`, `selection_changed{service_id, branch_id,
dentist_id, date, time}`, `booked{booking_id, service_id, date, time, dentist_id, branch_id}`,
`appointment_changed{appointment_id, action, date, time, fee}`, `callback_requested{callback_id,
reason, urgency}`, `language_requested{language}`. Every one carries `by: "visitor" | "agent"`.

## Rules the brain keeps

- **Credentials are typed, never spoken** (FEEDBACK X9). The patient types the mobile number and
  the code. The brain never asks for, fills, reads back or hears them: no move fills them, no
  event carries them, a number or code heard in speech is withheld from the model
  (`backend/credentials.py`), and the brain finds a patient only by id. On a typed sign-in
  (`patient_signed_in`, `by: visitor`, not `restored`) the agent welcomes the patient by first
  name in the next quiet moment and carries on with what they were doing; on `wrong_code` or
  `bad_phone` she says it did not go through and asks them to type it again; on `name_needed`
  she asks the new patient's name (a name is not a credential, `patient.name` fills it).

- Facts only from the data: prices, durations, dentists, rules, policies, instructions. Slots only
  from the engine.
- Booking, rescheduling and cancelling need a verified patient and a spoken **yes** to the summary
  on screen; `book.confirm` / `appt.apply` are sent only then (the visitor may also press Confirm).
- Clinical questions (bleeding, swelling with fever, which medicine, stopping a medicine, pregnancy,
  worsening pain) are never answered: the agent offers a dentist's callback (`callback.request`),
  and for the red-flag signs says the authored red-flag line first.

## Redial (v2, SDK 0.15.0 `Config.redial`)

A dropped brain socket does not end the call. Where Voqalize offers redial (`session.can_redial`),
`on_session_start` turns it on in the same configure as the voice, before the greeting; where it
does not, nothing is asked and the call runs as before. Each live brain is kept in this process by
session id (`backend/rejoin.py`) while its socket is up and for two minutes after it drops. A
redial that reaches the same process adopts the call as it was: the language and page, the call's
own calendar (with what this browser booked, moved or cancelled laid over it), the verified
patient and the code state, the held slot, the change waiting for a yes, the numbers minted so
far, a line waiting to be said, the model's history and the Stage director. No greeting is sent
on the new socket. A redial that reaches a fresh process (a deploy of the brain) finds nothing
and starts a new conversation on the same page. The brain cannot tell a hang-up from a drop (the
SDK does not hand it the End frame), so a hung-up call is let go by the same two-minute expiry.
The page changes nothing for this.
