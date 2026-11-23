/**
 * The agent's moves, made on Paynora's screens as its voice reaches them.
 *
 * Each performer brings the right screen up through the app's own router,
 * waits for its target, rings it, and only then acts, through the SAME
 * controller actions the buttons call (so `by` comes out as "agent" while the
 * move acts). It refuses with what the page offers rather than guessing, and
 * returns one short line the agent can repeat. Approving a payroll run is not
 * here: the admin presses that button.
 */
import { findThing, fold, type MoveContext, type Moves, type Performers, things, visible, waitFor } from "@voqalize/stage";
import { COMPANY, SLIP_MONTHS } from "../lib/data";
import { date, monthLabel, parseRupees, rupees } from "../lib/format";
import { comparisonOf, formProblems, GRADES, NEW_FIELDS, type NewField } from "../lib/payroll";
import { PAGES, type PageName, ROUTE_PATTERNS } from "../lib/routes";
import { SETUP_FIELDS, SETUP_STEPS, type SetupStep, STEP_TITLES, setupField } from "../lib/setup";
import { currentPath, go } from "../state/nav";
import * as S from "../state/store";
import { scene } from "./scene.gen";

type Spec = typeof scene.spec;

const WAIT_MS = 3000;
const $ = <T extends Element = HTMLElement>(sel: string) => document.querySelector<T>(sel);
const pathOnly = () => currentPath().split("?")[0]!.replace(/\/+$/, "") || "/";

/** Bring `to` up unless it is already in front, then wait for `sel` to render. */
async function open(to: string, sel: string, c: MoveContext, what: string): Promise<HTMLElement> {
  const [p, q = ""] = to.split("?");
  const here = currentPath();
  const samePath = pathOnly() === p;
  const sameQuery = !q || here.includes(`?${q}`) || here.includes(`&${q}`);
  if (!samePath || !sameQuery) go(to);
  const el = await waitFor(() => $<HTMLElement>(sel), WAIT_MS);
  return el ?? c.refuse("page", `${what} did not come up`);
}

const heading = () => $("[data-stage-heading]");
async function ringHeading(c: MoveContext) {
  const h = await waitFor(() => heading(), WAIT_MS);
  if (h && visible(h)) {
    await c.scrollTo(h);
    await c.ring(h, h.textContent ?? undefined);
  }
}

async function ringEl(c: MoveContext, el: Element, label: string) {
  await c.scrollTo(el);
  await c.ring(el, label);
}

/** A controller result as the move's detail, or its refusal. */
const landed = (r: S.Result, c: MoveContext, arg: string): string => (r.ok ? r.detail : c.refuse(arg, r.why, r.options));

const labelOf = (el: Element) => things().find((t) => t.el === el)?.label ?? el.textContent?.trim().slice(0, 60) ?? "";

function employeeOr(c: MoveContext, id: string, arg = "employee_id") {
  const want = (id ?? "").trim().toUpperCase();
  const e = S.employee(want) ?? S.useTk.getState().employees.find((x) => fold(x.name) === fold(id ?? ""));
  return e ?? c.refuse(arg, `there is no employee ${id}`, ["BB-1030 Ravi Kumar", "BB-1007 Kavitha Menon"]);
}

// ------------------------------------------------------------ setup helpers

async function openSetupStep(step: SetupStep, c: MoveContext) {
  await open("/welcome", "[data-setup-step]", c, "the setup wizard");
  if (S.useTk.getState().setup.step === step) return;
  const tab = $(`[data-setup-step="${step}"]`);
  if (tab) await ringEl(c, tab, STEP_TITLES[step]);
  S.setSetupStep(step);
}

// ------------------------------------------------------------ new-employee helpers

const FIELD_ALIASES: Record<string, NewField> = {
  designation: "title",
  role: "title",
  ctc: "annual_ctc",
  salary: "annual_ctc",
  manager: "manager_id",
  regime: "tax_regime",
  date_of_joining: "joined",
  joining_date: "joined",
  doj: "joined",
  city: "location",
  full_name: "name",
};
const FIELD_LABEL: Record<NewField, string> = {
  name: "Full name",
  email: "Work email",
  gender: "Gender",
  department: "Department",
  title: "Designation",
  grade: "Grade",
  location: "Location",
  joined: "Date of joining",
  annual_ctc: "Annual CTC",
  tax_regime: "Tax regime",
  manager_id: "Reporting manager",
};

function newField(raw: string, c: MoveContext): NewField {
  const k = fold(raw ?? "").replace(/[\s-]+/g, "_");
  const hit = (NEW_FIELDS as readonly string[]).find((f) => f === k) ?? FIELD_ALIASES[k];
  return (hit as NewField) ?? c.refuse("field", `the new-employee form has no field "${raw}"`, [...NEW_FIELDS]);
}

const MONTHS: Record<string, string> = { jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06", jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12" };
function isoDate(raw: string): string | null {
  const s = raw.trim().toLowerCase();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const m = /^(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*,?\s+(\d{4})$/.exec(s);
  if (m && MONTHS[m[2]!]) return `${m[3]}-${MONTHS[m[2]!]}-${m[1]!.padStart(2, "0")}`;
  return null;
}

/** The value as the form takes it, and how to say it back; refuses with the field's options. */
function normalNew(field: NewField, raw: string, c: MoveContext): [string, string] {
  const v = String(raw ?? "").trim();
  const st = S.useTk.getState();
  switch (field) {
    case "gender": {
      const g = /^(f|female|woman)$/i.test(v) ? "F" : /^(m|male|man)$/i.test(v) ? "M" : null;
      return g ? [g, g === "F" ? "female" : "male"] : c.refuse("value", "gender is F or M", ["F", "M"]);
    }
    case "department": {
      const d = COMPANY.company.departments.find((x) => fold(x) === fold(v)) ?? COMPANY.company.departments.find((x) => fold(x).startsWith(fold(v)));
      return d ? [d, d] : c.refuse("value", `there is no department "${v}"`, COMPANY.company.departments);
    }
    case "grade": {
      const g = `G${v.replace(/\D/g, "")}`;
      return GRADES.includes(g) ? [g, g] : c.refuse("value", `grade is one of ${GRADES.join(", ")}`, GRADES);
    }
    case "location": {
      const l = COMPANY.company.locations.find((x) => fold(x.city) === fold(v) || (fold(v) === "delhi" && x.city === "New Delhi"));
      return l ? [l.city, l.city] : c.refuse("value", `Banyan & Bay has no office in "${v}"`, COMPANY.company.locations.map((x) => x.city));
    }
    case "joined": {
      const d = isoDate(v);
      if (!d) c.refuse("value", "a date like 2026-02-16");
      if (!/^2026-02-(0[1-9]|1\d|2[0-8])$/.test(d)) c.refuse("value", "this form adds February 2026 joiners: a date from 2026-02-01 to 2026-02-28");
      return [d, date(d)];
    }
    case "annual_ctc": {
      const n = parseRupees(v);
      return n && n >= 120000 ? [String(n), rupees(n)] : c.refuse("value", "the annual CTC in rupees, like 720000");
    }
    case "tax_regime": {
      const r = /^new/i.test(v) ? "new" : /^old/i.test(v) ? "old" : null;
      return r ? [r, `the ${r} regime`] : c.refuse("value", "new or old", ["new", "old"]);
    }
    case "manager_id": {
      const e = S.employee(v.toUpperCase(), st) ?? st.employees.find((x) => fold(x.name) === fold(v));
      return e ? [e.id, `${e.name}, ${e.id}`] : c.refuse("value", `there is no employee "${v}" to report to`);
    }
    case "email":
      return /^\S+@\S+\.\S+$/.test(v) ? [v, v] : c.refuse("value", "an email address");
    default:
      return v ? [v, v] : c.refuse("value", `say the ${FIELD_LABEL[field].toLowerCase()}`);
  }
}

// ------------------------------------------------------------ performers

export function performers(): Performers<Spec> {
  return {
    "app.go": async ({ page }, c) => {
      const names = Object.keys(PAGES) as PageName[];
      const want = fold(String(page ?? "").trim());
      const name = names.find((n) => fold(n) === want) ?? names.find((n) => fold(n).startsWith(want) && want.length > 2) ?? c.refuse("page", `there is no page "${page}"`, names);
      const link = $(`[data-nav="${name}"]`);
      if (link && visible(link)) await ringEl(c, link, name);
      await open(PAGES[name], "[data-stage-heading]", c, name);
      c.done(`opened ${name}`);
      c.after(() => ringHeading(c));
      return `opened ${name}`;
    },

    "app.show": async ({ thing }, c) => {
      const said = String(thing ?? "");
      let el = findThing(said);
      if (!el || !visible(el as HTMLElement)) {
        // A part that lives on another tab of this page (Leave's Balances, Tax's Form 16): open that tab first.
        const tab = [...document.querySelectorAll<HTMLAnchorElement>(".tabs .tab, .me-tabs .me-tab")].find((t) => fold(t.textContent ?? "").includes(fold(said)) && fold(said).length > 2);
        if (tab) {
          await ringEl(c, tab, tab.textContent ?? said);
          tab.click();
          el = await waitFor(() => {
            const hit = findThing(said);
            return hit && visible(hit as HTMLElement) ? hit : null;
          }, WAIT_MS);
        }
      }
      if (!el || !visible(el as HTMLElement)) {
        const offered = [...new Set(things().filter((t) => visible(t.el as HTMLElement)).map((t) => t.label).filter(Boolean))];
        return c.refuse("thing", `nothing on this screen is called "${thing}"`, offered.slice(0, 24));
      }
      await c.reveal(el);
      const label = labelOf(el);
      await ringEl(c, el, label);
      return `showed ${label}`;
    },

    "app.open": async ({ path }, c) => {
      let p = String(path ?? "").trim();
      try {
        if (/^https?:/.test(p)) p = new URL(p).pathname + new URL(p).search;
      } catch {
        /* not a URL */
      }
      const base = import.meta.env.BASE_URL.replace(/\/$/, "");
      if (p.startsWith(base)) p = p.slice(base.length) || "/";
      if (!p.startsWith("/")) p = `/${p}`;
      const [bare, query] = p.split("?");
      const clean = bare!.replace(/\/+$/, "") || "/";
      const examples = ["/", "/employees/BB-1030", "/leave", "/tax/regime/BB-1007", "/me/BB-1030/payslips", "/welcome"];
      if (!ROUTE_PATTERNS.some((r) => r.test(clean))) c.refuse("path", `Paynora has no screen at ${clean}`, examples);
      const id = /BB-\d{4}/.exec(clean)?.[0];
      if (id && !S.employee(id)) c.refuse("path", `there is no employee ${id}`, examples);
      const run = /PR-\d{4}-\d{2}/.exec(clean)?.[0];
      if (run && !S.useTk.getState().runs.some((r) => r.id === run)) c.refuse("path", `there is no payroll run ${run}`, ["/payroll"]);
      await open(clean + (query ? `?${query}` : ""), "[data-stage-heading]", c, clean);
      c.done(`opened ${clean}`);
      c.after(() => ringHeading(c));
      return `opened ${clean}`;
    },

    "payslip.compare": async ({ employee_id, month, against }, c) => {
      const e = employeeOr(c, employee_id);
      const have = (S.useTk.getState().payslips[e.id] ?? []).map((s) => s.month);
      const offered = SLIP_MONTHS.filter((m) => have.includes(m));
      const m = String(month ?? "").slice(0, 7);
      if (!offered.includes(m)) c.refuse("month", `${e.name} has payslips for ${offered.map(monthLabel).join(", ")}`, offered);
      const a = against ? String(against).slice(0, 7) : null;
      if (a && (!offered.includes(a) || a === m)) c.refuse("against", `compare with another month on file`, offered.filter((x) => x !== m));
      await open(`/payslips/${e.id}/${m}${a ? `?against=${a}` : ""}`, ".slip", c, "the payslip");
      if (a && !currentPath().includes(`against=${a}`)) go(`/payslips/${e.id}/${m}?against=${a}`, true);
      const target = await waitFor(() => (a ? $(".difference") : $(".slip-net")), WAIT_MS);
      const s = S.slipOf(e.id, m)!;
      const p = a ? S.slipOf(e.id, a)! : null;
      const line = p
        ? `${e.name}'s ${monthLabel(m)} payslip against ${monthLabel(a!)}: net ${rupees(p.net_pay)} → ${rupees(s.net_pay)}`
        : `${e.name}'s ${monthLabel(m)} payslip: net ${rupees(s.net_pay)}`;
      if (target) await ringEl(c, target, p ? "Difference" : "Net pay");
      return line;
    },

    "regime.compare": async ({ employee_id }, c) => {
      const e = employeeOr(c, employee_id);
      await open(`/tax/regime/${e.id}`, ".regime-cards", c, "the regime comparison");
      const cards = [...document.querySelectorAll(".regime-card")];
      await c.scrollTo(cards[0]!);
      await c.ring(cards, { label: "New and old regime", separate: true });
      const cmp = comparisonOf(S.employee(e.id)!, S.useTk.getState().declarations);
      return `${e.name}: new regime ${rupees(cmp.new.total_tax)}, old regime ${rupees(cmp.old.total_tax)}; ${cmp.saving ? `${cmp.better} is lower by ${rupees(cmp.saving)}` : "equal"}; TDS is on the ${e.tax_regime} regime`;
    },

    "leave.decide": async ({ request_id, decision }, c) => {
      const id = String(request_id ?? "").trim().toUpperCase();
      const pending = S.pendingLeave().map((r) => r.id);
      const req = S.useTk.getState().leave.find((r) => r.id === id) ?? c.refuse("request_id", `there is no leave request ${request_id}`, pending);
      if (req.status !== "pending") c.refuse("request_id", `${id} is already ${req.status}`, pending);
      if (decision !== "approve" && decision !== "reject") c.refuse("decision", "approve or reject", ["approve", "reject"]);
      const btn = await open("/leave?tab=requests", `[data-request="${id}"] [data-decide="${decision}"]`, c, `request ${id}`);
      await ringEl(c, btn, `${decision === "approve" ? "Approve" : "Reject"} ${id}`);
      await c.beat(300);
      const r = decision === "approve" ? S.approveLeave(id) : S.rejectLeave(id);
      const detail = landed(r, c, "request_id");
      return detail;
    },

    "claim.fix": async ({ claim_id, amount }, c) => {
      const id = String(claim_id ?? "").trim().toUpperCase();
      const open_ = S.claimsToReview().map((x) => x.id);
      const claim = S.useTk.getState().claims.find((x) => x.id === id) ?? c.refuse("claim_id", `there is no claim ${claim_id}`, open_);
      if (claim.status !== "needs_fix" && claim.status !== "pending") c.refuse("claim_id", `${id} is already ${claim.status}`, open_);
      const n = Number(amount);
      if (n !== claim.bill_amount) c.refuse("amount", `the bill for ${id} is ${rupees(claim.bill_amount)}; a fix sets the claim to the bill`, [String(claim.bill_amount)]);
      const sel = claim.amount !== claim.bill_amount ? `[data-fix="${id}"]` : `[data-claim="${id}"] [data-decide="approve"]`;
      const btn = await open("/reimbursements", sel, c, `claim ${id}`);
      const bill = $(`[data-claim="${id}"] [data-stage-label="Bill amount"]`);
      await ringEl(c, bill ?? btn, `Bill ${rupees(claim.bill_amount)}`);
      await ringEl(c, btn, "Fix amount");
      const r = S.fixClaim(id, n);
      const detail = landed(r, c, "claim_id");
      return detail;
    },

    "claim.decide": async ({ claim_id, decision }, c) => {
      const id = String(claim_id ?? "").trim().toUpperCase();
      const open_ = S.claimsToReview().map((x) => x.id);
      const claim = S.useTk.getState().claims.find((x) => x.id === id) ?? c.refuse("claim_id", `there is no claim ${claim_id}`, open_);
      if (claim.status !== "needs_fix" && claim.status !== "pending") c.refuse("claim_id", `${id} is already ${claim.status}`, open_);
      if (decision !== "approve" && decision !== "reject") c.refuse("decision", "approve or reject", ["approve", "reject"]);
      if (decision === "approve" && claim.status === "needs_fix") {
        c.refuse("decision", `${id} claims ${rupees(claim.amount)} against a bill of ${rupees(claim.bill_amount)}; fix the amount first`, [String(claim.bill_amount)]);
      }
      const btn = await open("/reimbursements", `[data-claim="${id}"] [data-decide="${decision}"]`, c, `claim ${id}`);
      await ringEl(c, btn, `${decision === "approve" ? "Approve" : "Reject"} ${id}`);
      await c.beat(300);
      const r = S.decideClaim(id, decision);
      const detail = landed(r, c, "claim_id");
      return detail;
    },

    "employee.fill": async ({ field, value }, c) => {
      const f = newField(String(field ?? ""), c);
      const [v, said] = normalNew(f, String(value ?? ""), c);
      const input = await open("/employees/new", `[data-field="${f}"] input, [data-field="${f}"] select`, c, "the new-employee form");
      const box = input.closest("[data-field]") ?? input;
      await ringEl(c, box, FIELD_LABEL[f]);
      S.setNewField(f, v);
      return `${FIELD_LABEL[f]} set to ${said}`;
    },

    "employee.save": async (_a, c) => {
      if (pathOnly() !== "/employees/new") c.refuse("form", "the new-employee form is not open; fill its fields first");
      const st = S.useTk.getState();
      const problems = formProblems(st.newForm, st.employees.map((e) => e.id));
      const missing = Object.keys(problems);
      if (missing.length) c.refuse("form", `the form still needs ${missing.map((k) => FIELD_LABEL[k as NewField].toLowerCase()).join(", ")}`, missing);
      const btn = (await waitFor(() => $("[data-save-employee]"), WAIT_MS)) ?? c.refuse("form", "the Save button is not on screen");
      await ringEl(c, btn, "Save");
      await c.beat(300);
      const id = S.nextEmployeeId();
      const r = S.saveEmployee();
      const detail = landed(r, c, "form");
      go(`/employees/${id}`);
      return detail;
    },

    "regime.switch": async ({ employee_id, regime }, c) => {
      const e = employeeOr(c, employee_id);
      if (regime !== "new" && regime !== "old") c.refuse("regime", "new or old", ["new", "old"]);
      if (e.tax_regime === regime) c.refuse("regime", `${e.name} is already on the ${regime} regime`, [regime === "new" ? "old" : "new"]);
      if (S.locked()) c.refuse("employee_id", "the February run is approved and locked");
      await open(`/tax/regime/${e.id}`, "[data-switch-regime]", c, "the regime comparison");
      const panel = $('[data-stage-label="Switch regime"]')!;
      await ringEl(c, panel, "Switch regime");
      await c.beat(300);
      const r = S.switchRegime(e.id, regime);
      const detail = landed(r, c, "employee_id");
      c.done(detail);
      c.after(async () => {
        const tds = $('[data-stage-label="TDS for months left"]');
        if (tds) await ringEl(c, tds, "TDS for months left");
      });
      return detail;
    },

    "ticket.draft": async ({ subject, summary, employee_id }, c) => {
      if (!String(subject ?? "").trim()) c.refuse("subject", "a ticket needs a subject");
      if (!String(summary ?? "").trim()) c.refuse("summary", "a ticket needs the written summary");
      let who: string | null = null;
      if (employee_id) who = employeeOr(c, employee_id).id;
      const panel = await open("/help", ".handoff", c, "the help centre");
      await ringEl(c, panel, "Hand-off ticket");
      const r = S.draftTicket({ subject: String(subject), summary: String(summary), employee_id: who });
      const detail = landed(r, c, "summary");
      return detail;
    },

    "ticket.submit": async (_a, c) => {
      const d = S.useTk.getState().ticketDraft;
      if (!d?.subject.trim() || !d.summary.trim()) c.refuse("ticket", "there is no ticket draft on screen; draft one first");
      const btn = await open("/help", "[data-send-ticket]", c, "the hand-off panel");
      await ringEl(c, btn, "Send ticket");
      await c.beat(300);
      const r = S.submitTicket();
      const detail = landed(r, c, "ticket");
      return detail;
    },

    "setup.step": async ({ step }, c) => {
      if (!(SETUP_STEPS as readonly string[]).includes(step)) c.refuse("step", "setup has six steps", [...SETUP_STEPS]);
      await open("/welcome", `[data-setup-step="${step}"]`, c, "the setup wizard");
      const tab = $(`[data-setup-step="${step}"]`)!;
      await ringEl(c, tab, STEP_TITLES[step]);
      S.setSetupStep(step);
      return `on the ${STEP_TITLES[step].toLowerCase()} step`;
    },

    "setup.fill": async ({ field, value }, c) => {
      const f = setupField(String(field ?? "").trim()) ?? c.refuse("field", `setup has no field "${field}"`, SETUP_FIELDS.map((x) => x.name));
      // The field's step is opened if another is in front (and rung first).
      await openSetupStep(f.step, c);
      const input = (await waitFor(() => $(`[data-setup-field="${f.name}"]`), WAIT_MS)) ?? c.refuse("field", `${f.label} is not on screen`);
      await ringEl(c, input.closest("label") ?? input, f.label);
      const r = S.setSetupField(f.name, String(value ?? ""));
      const detail = landed(r, c, "value");
      return detail;
    },

    "setup.import": async (_a, c) => {
      await openSetupStep("import", c);
      const btn = (await waitFor(() => $("[data-import]"), WAIT_MS)) ?? c.refuse("step", "the import step is not on screen");
      await ringEl(c, btn.closest(".dropzone") ?? btn, "Import employees");
      const r = S.importEmployees();
      const detail = landed(r, c, "step");
      c.done(detail);
      c.after(async () => {
        const v = await waitFor(() => $(".validation"), WAIT_MS);
        if (v) await ringEl(c, v, "Validation summary");
      });
      return detail;
    },

    "setup.test_run": async (_a, c) => {
      if (!S.useTk.getState().setup.imported) c.refuse("step", "import employees first, on the import step", ["setup.import"]);
      await openSetupStep("test_run", c);
      const btn = (await waitFor(() => $("[data-test-run]"), WAIT_MS)) ?? c.refuse("step", "the test payroll step is not on screen");
      await ringEl(c, btn, "Run test payroll");
      const r = S.runTestPayroll();
      const detail = landed(r, c, "step");
      c.done(detail);
      c.after(async () => {
        const t = await waitFor(() => $(".test-totals"), WAIT_MS);
        if (t) await ringEl(c, t, "Test totals");
      });
      return detail;
    },

    "setup.finish": async (_a, c) => {
      if (!S.useTk.getState().setup.test) c.refuse("setup", "run the test payroll before finishing", ["setup.test_run"]);
      await openSetupStep("done", c);
      const btn = (await waitFor(() => $("[data-finish-setup]"), WAIT_MS)) ?? c.refuse("setup", "the last step is not on screen");
      await ringEl(c, btn, "Finish setup");
      await c.beat(300);
      const r = S.finishSetup();
      const detail = landed(r, c, "setup");
      go("/");
      return detail;
    },

    "me.view": async ({ employee_id, tab }, c) => {
      const e = employeeOr(c, employee_id);
      const tabs = ["payslips", "tax", "declarations", "leave"];
      const t = tab ?? "payslips";
      if (!tabs.includes(t)) c.refuse("tab", "the employee view has four tabs", tabs);
      const banner = await open(`/me/${e.id}/${t}`, ".viewas-banner", c, "the employee view");
      await ringEl(c, banner, `Viewing as ${e.name}`);
      return `viewing as ${e.name}, ${t}`;
    },
  };
}

/** Register every move the spec declares (a missing one does not compile). */
export function registerMoves(moves: Moves) {
  scene.registerAll(moves, performers());
}
