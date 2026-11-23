/**
 * The one controller. It holds the session's mutable copy of company.json and
 * every change goes through one of its actions, by CONTRACT.md's
 * recomputation rules on engine.ts. Buttons call these actions; Stage
 * performers call the same ones after they ring. Each action sends the
 * contract's Stage state event (`emit` takes `by` from `moves.author()`).
 *
 * An action answers `{ ok: true, detail }` or `{ ok: false, why, options? }`,
 * so a performer can refuse with exactly what a button would have shown.
 */
import { create } from "zustand";
import { type Regime } from "../lib/engine";
import {
  ADMIN, type Claim, COMPANY, type Declaration, DRAFT_RUN_ID, type Employee, type LeaveRequest, type PayrollRun, type Slip, type Ticket, TODAY,
} from "../lib/data";
import { delta, monthLabel, rupees } from "../lib/format";
import {
  type ImportResult, type NewEmployeeForm, type NewField, type RunTotals, declOf, emptyForm, employeeFromForm, febSlip, formProblems, joiningLop,
  leaveOutcome, parseCsv, REQUIRED_COLUMNS, reimbursementsFor, testPayroll, totalsOf, validateImport,
} from "../lib/payroll";
import { emptySetupFields, type SetupStep, setupField } from "../lib/setup";
import { emit } from "../stage/runtime";
import importCsv from "../../../data/employees_import.csv?raw";

export type Result = { ok: true; detail: string } | { ok: false; why: string; options?: string[] };
const ok = (detail: string): Result => ({ ok: true, detail });
const no = (why: string, options?: string[]): Result => ({ ok: false, why, ...(options?.length ? { options } : {}) });

export type TicketKind = "support" | "feature";
export const TICKET_KINDS: Record<TicketKind, string> = { support: "Support request", feature: "Feature request" };

export interface TicketDraft {
  kind: TicketKind;
  subject: string;
  summary: string;
  employee_id: string | null;
}

export interface SetupState {
  step: SetupStep;
  fields: Record<string, string>;
  imported: (ImportResult & { file: string }) | null;
  test: { totals: RunTotals; matched: number } | null;
  finished: boolean;
}

export interface Notice {
  id: number;
  text: string;
  tone: "positive" | "neutral" | "warning";
}

export interface TkState {
  employees: Employee[];
  payslips: Record<string, Slip[]>;
  /** Loss-of-pay days in the February draft, per employee. */
  febLop: Record<string, number>;
  runs: PayrollRun[];
  leave: LeaveRequest[];
  claims: Claim[];
  declarations: Declaration[];
  tickets: Ticket[];
  ticketDraft: TicketDraft | null;
  /** The hand-off drawer is open over the screen in front. */
  handoffOpen: boolean;
  /** The claim whose detail drawer is open on Reimbursements. */
  openClaim: string | null;
  newForm: NewEmployeeForm;
  setup: SetupState;
  notices: Notice[];
}

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

export function initialState(): TkState {
  const payslips = clone(COMPANY.payslips);
  const febLop: Record<string, number> = {};
  for (const [id, slips] of Object.entries(payslips)) febLop[id] = slips.find((s) => s.month === "2026-02")?.lop_days ?? 0;
  return {
    employees: clone(COMPANY.employees),
    payslips,
    febLop,
    runs: clone(COMPANY.payroll_runs),
    leave: clone(COMPANY.leave.requests),
    claims: clone(COMPANY.reimbursements.claims),
    declarations: clone(COMPANY.declarations),
    tickets: clone(COMPANY.tickets),
    ticketDraft: null,
    handoffOpen: false,
    openClaim: null,
    newForm: emptyForm(),
    setup: { step: "company", fields: emptySetupFields(), imported: null, test: null, finished: false },
    notices: [],
  };
}

export const useTk = create<TkState>(() => initialState());
const get = () => useTk.getState();
const set = (patch: Partial<TkState> | ((s: TkState) => Partial<TkState>)) => useTk.setState(patch);

// ------------------------------------------------------------ reads

export const employee = (id: string, s: TkState = get()) => s.employees.find((e) => e.id === id) ?? null;
export const nameOf = (id: string | null | undefined, s: TkState = get()) => (id ? (employee(id, s)?.name ?? id) : "—");
export const draftRun = (s: TkState = get()) => s.runs.find((r) => r.id === DRAFT_RUN_ID)!;
export const febSlipOf = (id: string, s: TkState = get()) => s.payslips[id]?.find((x) => x.month === "2026-02") ?? null;
export const slipOf = (id: string, month: string, s: TkState = get()) => s.payslips[id]?.find((x) => x.month === month) ?? null;
export const locked = (s: TkState = get()) => draftRun(s).status !== "draft";
export const pendingLeave = (s: TkState = get()) => s.leave.filter((r) => r.status === "pending");
export const claimsToReview = (s: TkState = get()) => s.claims.filter((c) => c.status === "pending" || c.status === "needs_fix");

let noticeId = 0;
export function notify(text: string, tone: Notice["tone"] = "positive") {
  const id = ++noticeId;
  set((s) => ({ notices: [...s.notices.slice(-2), { id, text, tone }] }));
  setTimeout(() => set((s) => ({ notices: s.notices.filter((n) => n.id !== id) })), 5200);
}

/** The February payslip of one employee, recomputed now. */
function computeFeb(e: Employee, s: TkState): Slip {
  return febSlip(e, s.febLop[e.id] ?? 0, declOf(e.id, s.declarations), reimbursementsFor(e.id, s.claims));
}

/** Recompute the named employees' February payslips and the draft's totals. */
function recompute(s: TkState, ids: string[]): Pick<TkState, "payslips" | "runs"> {
  const payslips = { ...s.payslips };
  for (const id of ids) {
    const e = employee(id, s);
    if (!e) continue;
    const others = (payslips[id] ?? []).filter((x) => x.month !== "2026-02");
    payslips[id] = [...others, computeFeb(e, s)];
  }
  const feb = s.employees.map((e) => payslips[e.id]?.find((x) => x.month === "2026-02")).filter((x): x is Slip => !!x);
  const t = totalsOf(feb);
  const runs = s.runs.map((r) => (r.id === DRAFT_RUN_ID ? { ...r, ...t } : r));
  return { payslips, runs };
}

/** What approving would do to February pay, without doing it. */
export function leaveImpact(id: string, s: TkState = get()) {
  const req = s.leave.find((r) => r.id === id);
  const e = req ? employee(req.employee_id, s) : null;
  if (!req || !e) return null;
  const out = leaveOutcome(req, e.leave_balance);
  const before = febSlipOf(e.id, s);
  let netChange = 0;
  if (out.lop && out.inFebruary && before) {
    const after = febSlip(e, (s.febLop[e.id] ?? 0) + out.lop, declOf(e.id, s.declarations), reimbursementsFor(e.id, s.claims));
    netChange = after.net_pay - before.net_pay;
  }
  return { ...out, netChange, employee: e };
}

/** A line saying what approving a request does: "1 day becomes LOP; Feb net −₹2,431". */
export function impactLine(id: string, s: TkState = get()): string {
  const i = leaveImpact(id, s);
  if (!i) return "";
  if (!i.lop) return `Covered by ${leaveTypeName(s.leave.find((r) => r.id === id)!.type)}; no pay change`;
  if (!i.inFebruary) return `${i.lop} ${i.lop === 1 ? "day" : "days"} become LOP in March; no change to February`;
  return `${i.lop} ${i.lop === 1 ? "day becomes" : "days become"} LOP; Feb net ${delta(i.netChange)}`;
}

export const leaveTypeName = (t: string) => ({ EL: "earned leave", CL: "casual leave", SL: "sick leave", LOP: "leave without pay" })[t] ?? t;

// ------------------------------------------------------------ actions

const lockedWhy = () => `the February run was approved by ${draftRun().approved_by} and is locked`;

export function approveLeave(id: string): Result {
  const s = get();
  const req = s.leave.find((r) => r.id === id);
  if (!req) return no(`there is no leave request ${id}`, pendingLeave(s).map((r) => r.id));
  if (req.status !== "pending") return no(`${id} is already ${req.status}`, pendingLeave(s).map((r) => r.id));
  const e = employee(req.employee_id, s)!;
  const out = leaveOutcome(req, e.leave_balance);
  if (out.lop && out.inFebruary && locked(s)) return no(lockedWhy());
  const before = febSlipOf(e.id, s);
  const balance = req.type === "LOP" ? e.leave_balance : { ...e.leave_balance, [req.type]: e.leave_balance[req.type as "EL"] - out.covered };
  const next: TkState = {
    ...s,
    employees: s.employees.map((x) => (x.id === e.id ? { ...x, leave_balance: balance } : x)),
    leave: s.leave.map((r) => (r.id === id ? { ...r, status: "approved", lop_days: out.lop } : r)),
    febLop: out.lop && out.inFebruary ? { ...s.febLop, [e.id]: (s.febLop[e.id] ?? 0) + out.lop } : s.febLop,
  };
  set({ ...next, ...(out.lop && out.inFebruary ? recompute(next, [e.id]) : {}) });
  const after = febSlipOf(e.id);
  emit("leave.decided", { request_id: id, decision: "approve", employee_id: e.id, lop_days: out.lop });
  let detail = `${id} approved for ${e.name}`;
  if (out.lop && out.inFebruary && before && after) {
    detail += `: ${out.lop} ${out.lop === 1 ? "day becomes" : "days become"} loss of pay; February net ${rupees(before.net_pay)} → ${rupees(after.net_pay)}`;
  } else if (out.lop) detail += `: ${out.lop} LOP ${out.lop === 1 ? "day" : "days"} fall in March, no February change`;
  else detail += `, covered by ${leaveTypeName(req.type)}`;
  notify(detail);
  return ok(detail);
}

export function rejectLeave(id: string): Result {
  const s = get();
  const req = s.leave.find((r) => r.id === id);
  if (!req) return no(`there is no leave request ${id}`, pendingLeave(s).map((r) => r.id));
  if (req.status !== "pending") return no(`${id} is already ${req.status}`, pendingLeave(s).map((r) => r.id));
  set({ leave: s.leave.map((r) => (r.id === id ? { ...r, status: "rejected" } : r)) });
  emit("leave.decided", { request_id: id, decision: "reject", employee_id: req.employee_id, lop_days: 0 });
  const detail = `${id} rejected for ${nameOf(req.employee_id)}`;
  notify(detail, "neutral");
  return ok(detail);
}

function changeClaim(id: string, patch: Partial<Claim>): Claim {
  const s = get();
  const c = { ...s.claims.find((x) => x.id === id)!, ...patch };
  const next = { ...s, claims: s.claims.map((x) => (x.id === id ? c : x)) };
  set({ ...next, ...(c.payroll_month === "2026-02" ? recompute(next, [c.employee_id]) : {}) });
  emit("claim.changed", { claim_id: id, status: c.status, amount: c.amount });
  return c;
}

export function fixClaim(id: string, amount?: number): Result {
  const s = get();
  const c = s.claims.find((x) => x.id === id);
  const open = claimsToReview(s).map((x) => x.id);
  if (!c) return no(`there is no claim ${id}`, open);
  if (c.status !== "needs_fix" && c.status !== "pending") return no(`${id} is already ${c.status}`, open);
  if (amount != null && amount !== c.bill_amount) return no(`the bill for ${id} is ${rupees(c.bill_amount)}; a fix sets the claim to the bill`, [String(c.bill_amount)]);
  if (c.payroll_month === "2026-02" && locked(s)) return no(lockedWhy());
  const was = c.amount;
  changeClaim(id, { amount: c.bill_amount, status: "approved", note: `Corrected from ${rupees(was)} to the bill, ${rupees(c.bill_amount)}.` });
  const detail = `${id} fixed to ${rupees(c.bill_amount)} and approved into ${nameOf(c.employee_id)}'s February pay`;
  notify(detail);
  return ok(detail);
}

export function decideClaim(id: string, decision: "approve" | "reject"): Result {
  const s = get();
  const c = s.claims.find((x) => x.id === id);
  const open = claimsToReview(s).map((x) => x.id);
  if (!c) return no(`there is no claim ${id}`, open);
  if (c.status !== "needs_fix" && c.status !== "pending") return no(`${id} is already ${c.status}`, open);
  if (decision === "approve" && c.status === "needs_fix") {
    return no(`${id} claims ${rupees(c.amount)} against a bill of ${rupees(c.bill_amount)}; fix the amount first`, [String(c.bill_amount)]);
  }
  if (decision === "approve" && c.payroll_month === "2026-02" && locked(s)) return no(lockedWhy());
  changeClaim(id, { status: decision === "approve" ? "approved" : "rejected" });
  const detail =
    decision === "approve"
      ? `${id} approved: ${rupees(c.amount)} joins ${nameOf(c.employee_id)}'s February pay`
      : `${id} rejected for ${nameOf(c.employee_id)}`;
  notify(detail, decision === "approve" ? "positive" : "neutral");
  return ok(detail);
}

export function switchRegime(id: string, regime: Regime): Result {
  const s = get();
  const e = employee(id, s);
  if (!e) return no(`there is no employee ${id}`);
  if (e.tax_regime === regime) return no(`${e.name} is already on the ${regime} regime`, [regime === "new" ? "old" : "new"]);
  if (TODAY > COMPANY.company.windows.proofs.closes) return no("the window for changing the regime closed on 28 Feb 2026");
  if (locked(s)) return no(lockedWhy());
  const before = febSlipOf(id, s);
  const next = { ...s, employees: s.employees.map((x) => (x.id === id ? { ...x, tax_regime: regime, regime_chosen_on: TODAY } : x)) };
  set({ ...next, ...recompute(next, [id]) });
  const after = febSlipOf(id)!;
  emit("regime.switched", { employee_id: id, regime });
  const detail = `${e.name} moved to the ${regime} regime; February TDS ${rupees(before?.tds ?? 0)} → ${rupees(after.tds)}`;
  notify(detail);
  return ok(detail);
}

export function setNewField(field: NewField, value: string) {
  set((s) => ({ newForm: { ...s.newForm, [field]: value } }));
}
export const resetNewForm = () => set({ newForm: emptyForm() });

export function nextEmployeeId(s: TkState = get()): string {
  const max = Math.max(...s.employees.map((e) => Number(e.id.slice(3))));
  return `BB-${max + 1}`;
}

export function saveEmployee(): Result {
  const s = get();
  const problems = formProblems(s.newForm, s.employees.map((e) => e.id));
  const missing = Object.keys(problems);
  if (missing.length) return no(`the form still needs: ${missing.map((k) => `${k} (${problems[k as NewField]})`).join("; ")}`, missing);
  if (locked(s)) return no(lockedWhy());
  const id = nextEmployeeId(s);
  const e = employeeFromForm(s.newForm, id);
  const lop = joiningLop(e.joined);
  const next = { ...s, employees: [...s.employees, e], febLop: { ...s.febLop, [id]: lop }, payslips: { ...s.payslips, [id]: [] } };
  set({ ...next, ...recompute(next, [id]), newForm: emptyForm() });
  emit("employee.added", {
    employee_id: id,
    name: e.name,
    gender: e.gender,
    department: e.department,
    title: e.title,
    grade: e.grade,
    location: e.location,
    joined: e.joined,
    annual_ctc: e.annual_ctc,
    tax_regime: e.tax_regime,
  });
  const slip = febSlipOf(id)!;
  const detail = `${e.name} added as ${id}; prorated February pay ${rupees(slip.net_pay)} net for ${slip.paid_days} of 28 days joins the draft`;
  notify(detail);
  return ok(detail);
}

export function draftTicket(d: Omit<TicketDraft, "kind"> & { kind?: TicketKind | null }): Result {
  if (!d.subject.trim() || !d.summary.trim()) return no("a ticket needs a subject and a summary");
  const kind: TicketKind = d.kind === "feature" ? "feature" : "support";
  set({ ticketDraft: { kind, subject: d.subject.trim(), summary: d.summary.trim(), employee_id: d.employee_id || null }, handoffOpen: true });
  return ok(`${TICKET_KINDS[kind].toLowerCase()} written out on screen: "${d.subject.trim()}"; nothing sent yet`);
}
export const editTicketDraft = (patch: Partial<TicketDraft>) =>
  set((s) => ({ ticketDraft: { kind: "support", subject: "", summary: "", employee_id: null, ...s.ticketDraft, ...patch } }));
export const discardTicketDraft = () => set({ ticketDraft: null, handoffOpen: false });
/** Open the hand-off drawer over the screen in front (a fresh draft of `kind`, or the one kept). */
export const openHandoff = (kind?: TicketKind) =>
  set((s) => ({
    handoffOpen: true,
    ticketDraft: kind && (!s.ticketDraft || (!s.ticketDraft.subject && !s.ticketDraft.summary)) ? { kind, subject: "", summary: "", employee_id: null } : s.ticketDraft,
  }));
/** Close the drawer; the draft is kept until it is sent or discarded. */
export const closeHandoff = () => set({ handoffOpen: false });

/** The claim detail drawer on Reimbursements (a click on a claim id, or `claim.open`). */
export const openClaimDrawer = (id: string) => set({ openClaim: id });
export const closeClaimDrawer = () => set({ openClaim: null });

export function submitTicket(): Result {
  const s = get();
  const d = s.ticketDraft;
  if (!d || !d.subject.trim() || !d.summary.trim()) return no("there is no ticket draft on screen; draft one first");
  const n = Math.max(...s.tickets.map((t) => Number(t.id.slice(3)))) + 1;
  const id = `TK-${n}`;
  set({ tickets: [{ id, subject: d.subject, summary: d.summary, status: "open", opened: TODAY, employee_id: d.employee_id, kind: d.kind }, ...s.tickets], ticketDraft: null, handoffOpen: false });
  emit("ticket.created", { ticket_id: id, subject: d.subject });
  const detail = `${TICKET_KINDS[d.kind ?? "support"].toLowerCase()} ${id} sent to Paynora's payroll team`;
  notify(detail);
  return ok(detail);
}

/** The admin's approval of a run: visitor only (paying people is never a move). */
export function approveRun(id: string): Result {
  const s = get();
  const run = s.runs.find((r) => r.id === id);
  if (!run) return no(`there is no run ${id}`);
  if (run.status !== "draft") return no(`${run.label} is already ${run.status}`);
  set({ runs: s.runs.map((r) => (r.id === id ? { ...r, status: "approved", approved_by: ADMIN.name } : r)) });
  emit("run.approved", { run_id: id, status: "approved" });
  const detail = `${run.label} payroll approved and locked; ${rupees(run.net_pay)} to be paid on 27 Feb 2026`;
  notify(detail);
  return ok(detail);
}

/** An employee uploads a proof for a declared item (self-service). */
export function uploadProof(employeeId: string, index: number): Result {
  const s = get();
  const d = s.declarations.find((x) => x.employee_id === employeeId);
  const item = d?.items[index];
  if (!d || !item) return no("there is no such declaration");
  if (TODAY > COMPANY.company.windows.proofs.closes) return no("the proof window closed on 28 Feb 2026");
  set({
    declarations: s.declarations.map((x) =>
      x.employee_id === employeeId ? { ...x, items: x.items.map((it, i) => (i === index ? { ...it, proof_status: "submitted" } : it)) } : x,
    ),
  });
  const detail = `Proof for ${item.label} uploaded; HR verifies it before 28 Feb 2026`;
  notify(detail);
  return ok(detail);
}

// ------------------------------------------------------------ setup

function setupEvent() {
  const st = get().setup;
  emit("setup.changed", {
    step: st.step,
    filled: Object.entries(st.fields)
      .filter(([, v]) => v.trim())
      .map(([k]) => k),
    imported: st.imported ? st.imported.rows.length : null,
    test_run: !!st.test,
    finished: st.finished,
  });
}
const patchSetup = (p: Partial<SetupState>) => set((s) => ({ setup: { ...s.setup, ...p } }));

export function setSetupStep(step: SetupStep): Result {
  if (get().setup.step === step) return ok(`on the ${step.replace("_", " ")} step`);
  patchSetup({ step });
  setupEvent();
  return ok(`on the ${step.replace("_", " ")} step`);
}

export function setSetupField(name: string, value: string, quiet = false): Result {
  const f = setupField(name);
  if (!f) return no(`setup has no field ${name}`);
  let v = value.trim();
  if (f.kind === "select" && f.options) {
    const hit = f.options.find((o) => o.toLowerCase() === v.toLowerCase()) ?? f.options.find((o) => o.toLowerCase().startsWith(v.toLowerCase()));
    if (!hit && v) return no(`${f.label} is one of the options`, f.options);
    v = hit ?? "";
  }
  if (["pan", "tan"].includes(name)) v = v.toUpperCase();
  if (f.kind === "number") v = v.replace(/[₹,%\s]|days?/gi, "");
  const bad = v && f.check ? f.check(v) : null;
  if (bad) return no(`${f.label} takes ${bad}`);
  set((s) => ({ setup: { ...s.setup, fields: { ...s.setup.fields, [name]: v } } }));
  if (!quiet) setupEvent();
  return ok(`${f.label} set to ${f.unit === "₹" ? rupees(Number(v)) : `${v}${f.unit === "%" ? "%" : f.unit ? ` ${f.unit}` : ""}`}`);
}

/**
 * "Use details from signup" (company) or "Use common defaults" (structure,
 * leave): every empty field of the step from its preset. The admin edits any
 * of them afterwards.
 */
export function fillPresets(step: SetupStep, fields: { name: string; preset: string }[]) {
  const cur = get().setup.fields;
  for (const f of fields) if (!cur[f.name]) setSetupField(f.name, f.preset, true);
  setupEvent();
  return ok(`${step} filled from ${step === "company" ? "signup" : "the common defaults"}`);
}

/** The sample employee file this demo ships (data/employees_import.csv), for the download link and tests. */
export const SAMPLE_IMPORT = importCsv;

/**
 * Import the file the admin chose with "Import file". Only she imports: the
 * guide has no move for it (owner, round 1, A1). Every row is checked before
 * anything is kept; a file without the expected columns is refused whole.
 */
export function importEmployees(text: string = importCsv, file = "employees_import.csv"): Result {
  const { header, rows } = parseCsv(text);
  const missing = REQUIRED_COLUMNS.filter((c) => !header.includes(c));
  if (!rows.length || missing.length) {
    const why = !rows.length ? `${file} has no rows` : `${file} is missing the columns ${missing.join(", ")}`;
    notify(why, "warning");
    return no(why);
  }
  const result = validateImport(rows);
  patchSetup({ imported: { ...result, file }, step: "import", test: null });
  setupEvent();
  return ok(`${file}: ${rows.length} rows, ${result.valid} valid, ${result.issues.length} ${result.issues.length === 1 ? "error" : "errors"}`);
}

export function runTestPayroll(): Result {
  const imp = get().setup.imported;
  if (!imp) return no("import employees first, on the import step", ["import"]);
  const valid = imp.rows.filter((r) => !imp.issues.some((i) => i.employee_id === r.employee_id));
  const { totals, matched } = testPayroll(valid);
  patchSetup({ test: { totals, matched }, step: "test_run" });
  setupEvent();
  return ok(
    `test payroll for ${monthLabel("2026-02")}, ${totals.employees} employees: gross ${rupees(totals.gross)}, TDS ${rupees(totals.tds)}, net ${rupees(totals.net_pay)}`,
  );
}

export function finishSetup(): Result {
  const st = get().setup;
  if (!st.test) return no("run the test payroll first", ["test_run"]);
  patchSetup({ finished: true, step: "done" });
  setupEvent();
  return ok("setup finished; the dashboard is next");
}

export const resetSession = () => useTk.setState(initialState(), true);
