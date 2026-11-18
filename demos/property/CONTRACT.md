# Kosha Homes — UI ↔ brain contract

Kosha Homes is a fictional residential developer (Bengaluru, Pune, Hyderabad) with a resale and rental
desk, Kosha Exchange. The agent is a property guide whose character, name, voices and languages live in
`persona.json` (today Karthik, English and Hindi). Both sides build against this file; change it only in
the same PR as the code.

## Data

- `data/homes.json` — the only source of facts, read by the page and the brain. Built by
  `data/build_data.py` (edit there, rerun). 50 listings (`new` units in 7 Kosha projects, `resale`,
  `rent`), 3 cities with drawn-map geometry (water, roads, metro lines, localities, places), lenders and
  EMI defaults, what to bring to a visit, each project's sales team and visiting hours, each city's
  Exchange desk.
- Nothing is invented at run time. Prices, rents, distances, slots and rates come from the file or from
  the rules below, which both sides implement identically.

## Shared rules (implemented twice: `backend/homes.py` and `frontend/src/data/`)

**Filter.** A listing matches when every set field holds: `city` equal; `deal` equal (`buy`|`rent`);
`bhk` contains its bhk; budget against `price` (buy) or `rent` (rent), `budget_min ≤ x ≤ budget_max`;
`possession` equal (`ready`|`under_construction`); `localities` contains its locality; `office` with
`max_km`: its `nearby.offices` entry for that office has `km ≤ max_km`; `school_km`: its nearest school
`km ≤ school_km`; `metro_km`: its nearest metro `km ≤ metro_km`; `amenities`: every one is in its
amenities. Unset fields do not filter. **Order:** with `office` set, by km to that office, then price;
otherwise by price (buy) or rent (rent) ascending, buy before rent; ties by id.

**EMI.** `principal = price × (1 − down_pct/100)`, `r = rate/1200`, `n = tenure_years × 12`,
`emi = round(principal × r × (1+r)^n / ((1+r)^n − 1))`. Defaults from `emi` in homes.json (20 %, 20
years, `sahyadri`). Only for `deal: buy`.

**Visit slots (IST).** The visit host is the project's `team` for a `new` listing, and the city's
`exchange` desk for `resale` and `rent`. Days: the 7 dates after today's date in Asia/Kolkata. A day's
weekday key is `mon`…`sun`; `hours[key]` null means closed. Slots start at `open`, every
`slot_minutes`, while `start + slot_minutes ≤ close`. A slot is free unless its HH:MM is in
`booked[key]` or a booking this browser made (page) / this call made or heard of (brain) holds that time with the
same host (host key: the project id for `new`, `exchange:<city>` otherwise).
Parts of the day: morning before 12:00, afternoon 12:00–15:59, evening from 16:00. Slot id
`YYYY-MM-DDTHH:MM`. Booking reference: `KV-<listing number>-<DD><HHMM>` (BLR-104 on the 22nd at 10:30 →
`KV-104-221030`). Visit address: the project's `address` (new) or the desk's `office` (resale, rent);
contact and phone from the host; what to bring from `bring[new|ready|resale|rent]` (`new` for an
under-construction unit, `ready` for a ready Kosha unit).

## Routes and agents (one brain, one job per landing)

| Route | Page | The agent's job there |
| --- | --- | --- |
| `/` | home: hero search, featured projects, cities | **guide** |
| `/listings` | sidebar filters, results, drawn map | **guide**: narrows the list, compares, EMI |
| `/listing/:id` | listing page with site-visit panel | **visit booker** |
| `/project/:id` | project page (configs, units, progress, location) | guide |
| `/compare?ids=a,b` | side by side | guide |
| `/shortlist`, `/visits` | saved homes, booked visits with visit cards | guide |

The call's `init` carries `{surface: "kosha-web", page: <path>, lang: "en"|"hi"}`. The brain starts in
the landing's job and follows `screen.viewed` to switch.

## Brain → page

All on-screen moves are **Stage** moves (`frontend/src/stage/scene.json`, generated to
`backend/stage_gen.py` and `frontend/src/stage/scene.gen.ts`): `site.go`, `listings.filter`,
`listings.show` (cue `{show: BLR-104}`), `compare.show`, `emi.show`, `shortlist.set`, `visit.slots`,
`visit.book`. Each performer rings before it acts, refuses with what the page offers, and returns one
short line. Markup: `data-stage-thing="listing:<id>"` (cards, map pins), `data-stage-part="<field>:<value>"`
on filter controls (`bhk:2`, `deal:buy`, `possession:ready`, `locality:Whitefield`, `amenity:Gym`,
`city:pune`), `data-stage-thing="visit-day:<YYYY-MM-DD>"`, `data-stage-part="slot:<slot id>"`.

One plain action besides Stage: `language_changed {language: "en"|"hi"}` (ui-command) moves the page's
language toggle when the call changes language.

## Page → brain

Stage events (`stage_event`), each with `by: visitor|agent`: `screen.viewed {path, page, listing_id?,
title?}` (every route change, silent), `search.changed {summary, count, …filters, ids}` (the first 12
result ids), `shortlist.changed {count, ids}`, `visit.slot_picked {listing_id, slot}`, `visit.booked
{listing_id, slot, reference}` (speaks when the visitor booked by hand). Plus Stage's own
`stage_result` / `stage_hello` / `stage_progress`.

## Rules

- Everything works by click alone; the voice layer is an adapter over the same store.
- `?debug=1` shows a console that fires any Stage move by hand (it runs the registered performer).
- The agent books only after the buyer's spoken yes (`visit.book` is `confirmed`).
