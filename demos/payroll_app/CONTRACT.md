# Tankora app — UI ↔ brain contract

Tankora is a fictional Indian HRMS and payroll product. This demo is the product itself, signed in as
Meghna Rao (HR admin, BB-1004) of Banyan & Bay Foods Pvt. Ltd., a fictional customer. One brain, three
jobs (onboarding guide, in-app support, feature coach), one Stage scene. The character (name, face,
voices, languages) lives only in `persona.json`.

This file is the agreement between `frontend/` and `backend/`. Change it only together with the code.

## Data (ground truth for both sides)

- `data/product.json` — brand, palette, type, logo, modules, plans, FY 2025-26 tax rules.
- `data/company.json` — the customer: 56 employees, runs Apr 2025–Jan 2026 paid and Feb 2026 DRAFT,
  payslips (Nov, Dec, Jan, Feb draft), leave, reimbursements, declarations (with `engine.verified`, the
  engine's own `Declarations` input), Form 16, tickets, stories. The clock is frozen at `today`
  (2026-02-16). Regenerate with `cd demos && uv run python payroll_app/data/build_data.py`.
- `backend/payroll_engine.py` and `frontend/src/lib/engine.ts` — the same engine, held to
  `data/tax_fixtures.json`. Every recomputation (LOP from approved leave, prorated pay for a new
  joiner, regime switch TDS, regime comparison, the test payroll) uses it on both sides, so the screen
  and the voice give the same rupee.

## Recomputation rules (both sides do exactly this)

All on the **February 2026 draft** (`PR-2026-02`, month_idx 10, 28 days), from `ytd_to_jan` and the
employee's `engine.verified` declarations (empty `Declarations` when there is no declaration):

- **Feb payslip** = `payslip(pay, 10, 28, lop_days, ytd_to_jan, decl, reimbursements, regime)` where
  `pay = {ctc: annual_ctc, city: location, state, gender, lta_monthly, regime: tax_regime,
  first_month_idx}` (first_month_idx: 0 if joined before 2025-04-01, else the FY month index of joining).
  `reimbursements` = sum of the employee's claims with `payroll_month == "2026-02"` and status
  `approved`. The run's totals are the sums over employees (gross, employee_pf, employer_pf,
  employee_esi, employer_esi, professional_tax, tds, reimbursements, net_pay, lop_days) and
  `employer_cost` = gross + employer_pf + employer_esi. Unchanged, this reproduces company.json's draft.
- **Approve leave**: days beyond the balance of its type become LOP (`LOP` type: all days are LOP).
  The balance is reduced by the days it covers. If the leave falls in February 2026 the employee's Feb
  payslip is recomputed with those LOP days added; a March leave changes no Feb number. Reject: status
  only.
- **Fix claim**: amount := bill_amount, status := approved; if `payroll_month` is 2026-02 the amount joins
  that employee's Feb reimbursements (no TDS effect).
- **Approve / reject claim**: approve adds to Feb reimbursements as above.
- **Switch regime**: `tax_regime` := new value; Feb payslip recomputed with that regime (TDS for the
  months left = (year's tax under the new regime − TDS so far) / 2).
- **Add employee** (joined in Feb 2026): id `BB-1057` (then 1058…), structure from CTC and city
  (LTA by grade: G5 ₹3,000, G6+ ₹5,000, else 0), first_month_idx 10, ytd empty, LOP = day of joining − 1
  (days not yet joined), no declarations. Their prorated Feb payslip joins the draft; employees + 1.

## Routes (BrowserRouter, base `/demos/payroll_app/`)

| path | screen |
|---|---|
| `/welcome` | setup wizard: steps company, structure, import, leave, test_run, done |
| `/` | dashboard |
| `/employees`, `/employees/new`, `/employees/:id` | list, add form, detail |
| `/payroll`, `/payroll/:runId` | runs, run detail (register; approve flow for the draft) |
| `/payslips`, `/payslips/:employeeId/:month` (`?against=YYYY-MM`) | picker; payslip, optionally compared |
| `/leave` (`?tab=requests\|balances\|holidays\|policy`) | leave |
| `/reimbursements` | claims |
| `/tax` (`?tab=declarations\|regime\|form16`), `/tax/regime/:employeeId` | tax; regime comparison |
| `/settings` (`?tab=company\|statutory\|structure\|leave\|billing`) | settings |
| `/help` | help centre, tickets, hand-off panel |
| `/me/:employeeId/:tab`, `/me/:employeeId/payslips/:month` (`?against=`) | employee self-service (payslips, tax, declarations, leave) |

## Brain → page: Stage moves (`frontend/src/stage/scene.json`)

Generated with `uv run voqalize stage gen payroll_app/frontend/src/stage/scene.json --py
payroll_app/backend/stage_gen.py --ts payroll_app/frontend/src/stage/scene.gen.ts` (from `demos/`).
Cues: `{go: Leave}` and `{show: Label}`. Everything else is sent by a brain tool. `confirmed` moves are
sent only after the admin's spoken yes. Approving a payroll run (paying people) is **not** a move: the
admin presses that button.

`{show: Label}` rings the `[data-stage-thing]` whose `data-stage-label` (or name) matches. Labels the
brain uses (each screen marks these):

- Payslip: `Basic`, `HRA`, `LTA`, `Special allowance`, `Gross`, `Loss of pay`, `Provident fund`,
  `Professional tax`, `TDS`, `Reimbursements`, `Net pay`, `Difference`.
- Regime comparison: `New regime`, `Old regime`, `New regime slabs`, `Old regime slabs`,
  `Deductions`, `Switch regime`, `TDS for months left`, `Employee picker`.
- Leave: `Pending requests`, `Approve`, `Reject`, `Balances`.
- Reimbursements: `Claims to review`, `Bill amount`, `Fix amount`.
- Payroll run: `Review checklist`, `Payroll register`, `Approve run`, `Run totals`.
- Dashboard: `February draft`, `Alerts`, `Proof window`, `Headcount`.
- Tax: `Declarations`, `Proof status`, `Form 16`.
- Setup: one thing per step (`Company details`, `Pay structure`, `Import employees`,
  `Validation summary`, `Leave policy`, `Test payroll`, `Test totals`).
- Help: `Hand-off ticket`, `Send ticket`.

Results: a performer returns one short line (what landed). Refusals list what the page offers.

## Page → brain

Stage state events (`scene.event`, `by` from `moves.author()`): `screen.viewed` (silent),
`leave.decided`, `claim.changed`, `employee.added`, `regime.switched`, `ticket.created`,
`run.approved`, `setup.changed`. The brain applies a `by: "visitor"` change to its own copy of the data
with the rules above; its own moves it applies when their result comes back `applied`.

Typed app event (not Stage): `language_requested {language: "en"|"hi"}` from the EN / हिंदी toggle.
Brain → page site command (not Stage): `language_changed {language}` — the toggle follows.

`init` on connect: `{surface: "payroll_app", landing: <path>, lang: "en"|"hi"}`. The landing picks the
job: `/welcome` → onboarding; `/` and `/help` → support; anything else → coach. The brain follows
`screen.viewed` to switch job when the visitor moves to `/welcome` or away from it.

## Notes the page settled while building

- The setup wizard's test payroll joins each CSV row to company.json by `employee_id` for what a CSV
  does not carry (grade, LTA, year-to-date pay, declarations, leave, claims); the screen says that
  history came with the company's data from its previous payroll.
- Once the admin approves the February run it is locked: any change that would move February pay
  (leave that becomes LOP, a claim, a regime switch, a new joiner) is refused with "approved and locked".
- `{show: Label}` for a label on another tab of the same page (`Balances` on Leave, `Form 16` on Tax)
  opens that tab first, then rings.
- `setup.fill` opens the step that holds the field before ringing it.
- `employee.added`'s email is private in the slice, so it never reaches the brain.
