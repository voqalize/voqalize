# Paynora site — UI ↔ brain contract

Paynora is a fictional Indian HR and payroll SaaS; `payroll_site` is its marketing website, with
one voice agent (the character in `persona.json`) who does three jobs, one per landing page. This
file is the agreement between `frontend/` and `backend/`. Change it in the same PR as the code.

## Data (read by both sides, never copied)

- `data/product.json`: brand, modules (`min_plan`), plans, `pricing_rules`, customers, FY 2025-26 tax
  rules. A byte-for-byte copy of `payroll_app/data/product.json`; the e2e fails if it drifts.
- `data/tax_example.json`: the worked old-vs-new example on `/tax`. Never recomputed on the site.
- `content/site.json`: page copy, the lead card's vocabulary (pains → modules, current tools,
  states), the sales calendar (reps, weekly IST hours, holidays, the taken rule) and booking topics.
- `persona.json`: the character (name, avatar, voice per language, languages, default).

**Twins.** Pricing is `backend/pricing.py` and `frontend/src/lib/pricing.ts`, pinned by
`content/pricing_cases.json`. The calendar is `backend/calendar_rules.py` and
`frontend/src/lib/calendar.ts`, pinned by `content/calendar_cases.json`.

## Jobs, by landing page

`init` carries `{page, lang}`; the brain also follows Stage's `screen.viewed`.

| Route | Job | What the agent does |
| --- | --- | --- |
| `/` (and modules, tax, customers) | AI SDR | Qualifies (headcount, current tool, states, pains), fills the lead card field by field, marks the matching module cards, hands off to pricing or a demo |
| `/pricing` | Pricing explainer | Works out the plan per `plan_choice`, sets the calculator control by control, talks the breakdown through line by line |
| `/book-demo` | Demo booker | Shows the calendar, picks a free slot, fills the form, confirms only after a spoken yes |

## Stage moves (`frontend/src/stage/scene.json`)

Cues (in the agent's words): `{show: <section>}`, `{module: <id>}`, `{line: <breakdown key>}`.
Tool moves: `site.go`, `modules.highlight`, `lead.fill`, `pricing.set`, `calendar.show`,
`booking.pick`, `booking.fill`, `booking.confirm` (confirmed, after a yes in a later turn).
Slices and events: `screen.viewed` (silent), `lead.changed`, `pricing.changed`,
`booking.changed`, `booking.confirmed` (speak). The lead's email is private: the brain hears only
`has_email`.

Site command (not a move): `language_changed {language}` moves the EN / हिंदी toggle.

## Markup the performers find

| Attribute | On |
| --- | --- |
| `data-stage-thing="nav:<path>"` | each header link and the Book a demo button |
| `data-stage-thing="<section>"` + `data-stage-label` | page sections (`pain-points`, `modules`, `tax-showcase`, `customer-quotes`, `new-regime`, `old-regime`, `worked-example`, `deductions`, `statutory`, `tds-form16`, `plans`, `calculator`, `faq`, `calendar`, `booking-form`) |
| `data-stage-thing="module:<id>"` | every module card |
| `data-stage-thing="plan:<id>"` | the three plan cards |
| `data-stage-thing="lead-card"`, `data-stage-part="lead:<field>"` | the lead card and its rows |
| `data-stage-part="pricing:headcount"`, `pricing:module:<id>`, `pricing:billing`, `pricing:filing` | calculator controls |
| `data-stage-part="line:<key>"` | breakdown lines |
| `data-stage-part="day:<YYYY-MM-DD>"`, `slot:<slot id>` | calendar days and slots |
| `data-stage-part="booking:<field>"`, `booking:confirm` | booking form fields and its button |

## Rules

- Everything works by click alone through `src/state/store.ts`; performers call the same actions.
- The agent states only facts from the three data files; the email goes on the lead card or the
  booking form only when the visitor typed it, or said it and confirmed it when read back.
- Never a real company, product or person. "Current tool" options are generic.
