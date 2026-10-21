# Booking, payment, changes and cancellation

Sources: https://reservations.explora.com/ibe/paso1 (explored 2026-10-21, `L3/reservations.json`); https://www.explora.com/payment-and-cancellation-policies/ (crawl, completed from the live page 2026-10-21 because the crawl cut its tabs short); /offer/childrens-benefit-at-explora/; /2026/08/27/solo-travel-set-your-own-pace/; /join-the-explorer-echo-society/; /explora-contact/; /contact-explora-lodges/; /explora-expeditions/; every lodge page's CHECK AVAILABILITY button.

## How booking works
- **Lodges and the Travesía are booked online** on the booking site reservations.explora.com (every "CHECK AVAILABILITY" / "BOOK NOW" button opens `https://reservations.explora.com/ibe/paso1?language=EN` in a new tab, with no lodge preselected).
- **Step 1 — "PLEASE PROVIDE YOUR TRAVEL DETAILS"** (`/ibe/paso1`): (1) "Select HOTEL / TRAVESIA" — a dropdown grouped as New hotels (Opening Dec 2026), Hotels, Travesias, Expeditions; (2) "SELECT ARRIVAL DATE" — an always-open calendar (two months side by side on desktop) where only available days can be clicked; today cannot be chosen; (3) "Select the number of nights of your stay" — fills in after a date is picked, each option with a "from" nightly price (for example the label format is "5 nights (from US$ 1,140 / night)"), and the recommended stay is preselected. Then **Continue**.
- Changing the lodge reloads the page with its availability; step 1 has no adults/children/rooms fields.
- **Step 2 — Rooms** (`/ibe/paso2`): a rates table per room type; for each room choose "Room for" 1 Traveler or 2 Travelers and, for some rooms, King or Twin bed, then **Add this room**. A pop-up offers "I'm ready. Go to check-out", "Add more rooms" or "Add another Explora destination".
- **Step 3 — Contact info** (`/ibe/paso3`): title, first and last name (letters only, no accents), email, phone, nationality, accept terms, optional news opt-in, a guarantee option and a payment method (Webpay or Flywire), then "Review your order and pay". Steps 4–5 are payment and confirmation. The visitor completes payment themselves.
- **Rates vary by date and lodge**; the booking site shows the current "from" price per night for each length of stay. Do not quote a rate without looking it up there.
- **Expeditions are not booked on the calendar.** Choosing an expedition on step 1 opens an **enquiry form** (`/ibe/expeditions?expedition_request=CODE`): title, first name, last name, email, phone, nationality, message, an "I'm not a robot" tick box the visitor must tick themselves, then **SEND MESSAGE**. Expedition enquiries can also go to reserveexpeditions@explora.com.

### Booking codes (reservations.explora.com)
| Code | Label on the booking site | Group | Flow |
|---|---|---|---|
| ECFT | El Calafate, Patagonia Argentina | New hotels (Opening Dec 2026) | booking |
| ERTP | Torres del Paine - Conservation Reserve, Chile | New hotels (Opening Dec 2026) | booking |
| EATA | Atacama, Chile | Hotels | booking |
| ERAP | Easter Island, Chile | Hotels | booking |
| EPAT | Torres del Paine, Patagonia Chile | Hotels | booking |
| EPNP | Parque Nacional Patagonia, Chile | Hotels | booking |
| EVAL | Machu Picchu & Sacred Valley, Peru | Hotels | booking |
| ECHA | El Chaltén, Patagonia Argentina | Hotels | booking |
| PATA | Atacama & Uyuni (Chile to Bolivia) | Travesias | booking |
| PUYU | Uyuni & Atacama (Bolivia to Chile) | Travesias | booking |
| XICE | Iceland Expedition | Expeditions | enquiry |
| XICW | Iceland Winter Expedition | Expeditions | enquiry |
| XSCM | Sacred Mountains Expedition | Expeditions | enquiry |
| XTFG | Tierra del Fuego Expedition | Expeditions | enquiry |

`/ibe/paso1?hotel_code=CODE` preselects a lodge; adding `&check_in_date=YYYY-MM-DD` also preselects the date.

### Other ways to book or ask
Email **reserve@explora.com** (rates, availability, offers, changes) or use the form on /explora-contact/. Lodge reception emails and the call-tracked phone numbers are in `company`.

## Payment (/payment-and-cancellation-policies/, tab "Payments & Reservation")
These conditions apply only to individual travelers, not groups.
- **Lodges:** initial payment of up to 30% to confirm; balance due 30 days before check-in. **Holidays:** 50% deposit; balance 60 days before check-in.
- **Travesía Atacama–Uyuni:** down payment up to 30%; balance 60 days before check-in.
- **Expeditions:** down payment up to 30%, which includes a **non-refundable Reservation Fee** — USD 500 per person (Tierra del Fuego, Sacred Mountains) or USD 1,000 per person (Iceland); balance 120 days before check-in.
- **Explora Days or Cyber Week promotions:** 100% at booking.
- **Refunds:** processed within up to 60 calendar days of validating the request, to the original payment method. Transaction fee on refunds: 3% of the amount for credit card payments, USD 25 for bank transfers.

## Changes and cancellation (tabs "Booking changes", "Cancellation policies")
| Product | Free until | Then | Last stretch |
|---|---|---|---|
| Lodges | 30+ days before check-in | 29–15 days: 50% fine | 14–0 days: 100% |
| Travesía Atacama–Uyuni | 60+ days | 59–30 days: 50% | 29–0 days: 100% |
| Expeditions | 120+ days | 119–60 days: 50% | 59–0 days: 100% (Reservation Fee never refunded) |
| Holiday dates | 60+ days | 59–30 days: 50% | 29–0 days: 100% |

- **Holiday Season (Year-End):** Torres del Paine Dec 22, 2026 – Jan 1, 2027; Patagonia National Park Dec 24, 2026 – Jan 1, 2027; El Chaltén Dec 23, 2026 – Jan 1, 2027; Atacama Dec 22, 2026 – Jan 1, 2027; Easter Island Dec 22, 2026 – Jan 1, 2027; Sacred Valley Dec 23, 2026 – Jan 1, 2027. **Carnival (Atacama only):** Feb 5 – Feb 13, 2027. Minimum stays apply on holiday dates.
- **Rio Carnival and Tapati festivals:** special rates; minimum 4 nights at Explora Atacama and 3 nights at Explora Easter Island.
- **Special and last-minute offers:** cancel up to 30 days before → 30% of the total; 29–0 days → 100%.
- A booking modified once cannot then be cancelled (the original fine applies).
- **Third-party services** (for example trains to Machu Picchu): 100% of what the supplier charges Explora is applied on cancellation or change. The Machu Picchu exploration is **not available on two-night stays** at Explora Sacred Valley; for longer stays the page states USD 430 adults / USD 380 children up to 11 (see disagreements).
- **Disclaimer:** Explora Chile S.A. does not refund services lost to third-party flight or transport cancellations or delays, or force majeure (weather, road conditions, fires, earthquakes, floods, strikes and so on).

## Check-in and check-out
Check-in from 13:00, check-out 10:00; lunch not included on check-out day (see `getting-there-and-transfers`).

## Children and families (/offer/childrens-benefit-at-explora/)
- Under 2: free, in the parents' room.
- Ages 2–12: extra bed in the parents' room from USD 310 per child per night (maximum 1 child sharing).
- Ages 13–17: family rate from USD 360 per person per night in an additional room, double occupancy required (minimum 2 young guests per room, or 2 persons charged).
- Rates vary by season; available at most lodges, with seasonal variations; check dates with reserve@explora.com. At Rapa Nui the extra bed is only in the Suite category. Not for Travesías or Expeditions. Extra bed 1.9 m x 1.0 m; limited stock.

## Solo travelers
A single rate applies to private solo accommodation; there is no shared-room option (/2026/08/27/solo-travel-set-your-own-pace/). See `offers-and-programs` for the Solo Travelers Save 50% offer.

## Where the site disagrees with itself
- **Policy page metadata vs body:** the page title says "Terms and Conditions in explora hotels for year 2021" and its description says changes are free "up to seven (7) days before your check-in"; the body says 30 days for lodges. Quote the body.
- **Machu Picchu exploration price:** the desktop policy text says USD 430 adults / USD 380 children (with 2026 reference dates); a second copy on the same page (2025 reference dates) says USD 400 / USD 350; /corporate-travel-program/ says Machu Picchu "has an additional cost of US$350 per person". Say it carries an extra cost and confirm with reserve@explora.com.
- **Deposit:** the policy page says up to 30%; the Echo Society terms (/join-the-explorer-echo-society/) mention "the initial deposit (20%)" for online bookings.
- **Expedition cancellation:** the policy page uses a 120/60-day scale; the Tierra del Fuego FAQ states 60/30 days (see `expeditions-south-america`).
- **Holiday period:** policy page lists per-lodge dates (Dec 22/23/24 – Jan 1); Echo Society terms say benefits do not apply "between 21 December and 5 January".
