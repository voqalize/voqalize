/**
 * CONTRACT.md's recomputation rules, as pure functions over engine.ts. The
 * store calls these for every change to the February draft, and the setup
 * wizard's test payroll calls the same ones, so the screen and the brain give
 * the same rupee.
 */
import {
  type Declarations, type EmployeePay, FEBRUARY, emptyYtd, noDeclarations, type Payslip, payslip, type Regime, regimeComparison, structure,
  type Ytd,
} from "./engine";
import { type Claim, COMPANY, type Declaration, type Employee, type LeaveRequest, type Slip } from "./data";

export const FEB_DAYS = 28;
export const FEB = "2026-02";

/** The FY month index of a YYYY-MM month: April 0 … March 11. */
export const fyIndex = (ym: string): number => (Number(ym.slice(5, 7)) + 8) % 12;

/** 0 for someone who joined before the year began, else the FY month index of joining. */
export function firstMonthIdx(joined: string): number {
  if (joined < "2025-04-01") return 0;
  return fyIndex(joined.slice(0, 7));
}

export function payOf(e: Pick<Employee, "annual_ctc" | "location" | "state" | "gender" | "lta_monthly" | "tax_regime" | "joined">): EmployeePay {
  return {
    ctc: e.annual_ctc,
    city: e.location,
    state: e.state,
    gender: e.gender,
    lta_monthly: e.lta_monthly,
    regime: e.tax_regime,
    first_month_idx: firstMonthIdx(e.joined),
  };
}

/** The engine's own declarations input: the verified amounts, or none. */
export function declOf(id: string, declarations: Declaration[]): Declarations {
  return declarations.find((d) => d.employee_id === id)?.engine.verified ?? noDeclarations();
}

/** Claims approved into a payroll month, summed for one employee. */
export function reimbursementsFor(id: string, claims: Claim[], month = FEB): number {
  return claims.filter((c) => c.employee_id === id && c.payroll_month === month && c.status === "approved").reduce((n, c) => n + c.amount, 0);
}

/** The February draft payslip, by the contract's rule. */
export function febSlip(e: Employee, lopDays: number, decl: Declarations, reimbursements: number, ytd: Ytd = e.ytd_to_jan): Slip {
  const s = payslip(payOf(e), FEBRUARY, FEB_DAYS, lopDays, ytd, decl, reimbursements, e.tax_regime);
  return { ...s, month: FEB, regime: e.tax_regime, joining_days_unpaid: 0 };
}

export interface RunTotals {
  employees: number;
  gross: number;
  employee_pf: number;
  employer_pf: number;
  employee_esi: number;
  employer_esi: number;
  professional_tax: number;
  tds: number;
  reimbursements: number;
  net_pay: number;
  lop_days: number;
  employer_cost: number;
}

export function totalsOf(slips: Payslip[]): RunTotals {
  const t: RunTotals = {
    employees: slips.length,
    gross: 0,
    employee_pf: 0,
    employer_pf: 0,
    employee_esi: 0,
    employer_esi: 0,
    professional_tax: 0,
    tds: 0,
    reimbursements: 0,
    net_pay: 0,
    lop_days: 0,
    employer_cost: 0,
  };
  for (const s of slips) {
    t.gross += s.gross;
    t.employee_pf += s.employee_pf;
    t.employer_pf += s.employer_pf;
    t.employee_esi += s.employee_esi;
    t.employer_esi += s.employer_esi;
    t.professional_tax += s.professional_tax;
    t.tds += s.tds;
    t.reimbursements += s.reimbursements;
    t.net_pay += s.net_pay;
    t.lop_days += s.lop_days;
  }
  t.employer_cost = t.gross + t.employer_pf + t.employer_esi;
  return t;
}

/** What approving a leave request does to the balance and to pay. */
export function leaveOutcome(req: LeaveRequest, balance: Record<string, number>): { covered: number; lop: number; inFebruary: boolean } {
  const have = req.type === "LOP" ? 0 : Math.max(0, balance[req.type] ?? 0);
  const covered = Math.min(req.days, have);
  return { covered, lop: req.days - covered, inFebruary: req.from.startsWith(FEB) };
}

/** Both regimes for one employee, with verified declarations, from February. */
export function comparisonOf(e: Employee, declarations: Declaration[]) {
  return regimeComparison(payOf(e), e.ytd_to_jan, FEBRUARY, declOf(e.id, declarations));
}

/** TDS deducted in the year before `month` (YYYY-MM), from ytd_to_jan and the slips on file. */
export function tdsBefore(e: Employee, slips: Slip[], month: string): number {
  let tds = e.ytd_to_jan.tds;
  for (const s of slips) if (s.month >= month && s.month <= "2026-01") tds -= s.tds;
  return tds;
}

// ------------------------------------------------------------ new employee

/** LTA by grade, from the pay-structure rule. */
export const ltaForGrade = (grade: string): number => {
  const g = Number(grade.replace(/\D/g, ""));
  return g >= 6 ? 5000 : g === 5 ? 3000 : 0;
};

export const stateOfCity = (city: string): string | null => COMPANY.company.locations.find((l) => l.city === city)?.state ?? null;

export interface NewEmployeeForm {
  name: string;
  email: string;
  gender: string;
  department: string;
  title: string;
  grade: string;
  location: string;
  joined: string;
  annual_ctc: string;
  tax_regime: string;
  manager_id: string;
}
export const NEW_FIELDS = ["name", "email", "gender", "department", "title", "grade", "location", "joined", "annual_ctc", "tax_regime", "manager_id"] as const;
export type NewField = (typeof NEW_FIELDS)[number];
export const emptyForm = (): NewEmployeeForm => ({
  name: "",
  email: "",
  gender: "",
  department: "",
  title: "",
  grade: "",
  location: "",
  joined: "",
  annual_ctc: "",
  tax_regime: "new",
  manager_id: "",
});
export const GRADES = ["G1", "G2", "G3", "G4", "G5", "G6", "G7"];

/** What is still missing or wrong on the form, by field. */
export function formProblems(f: NewEmployeeForm, managers: string[]): Partial<Record<NewField, string>> {
  const out: Partial<Record<NewField, string>> = {};
  if (!f.name.trim()) out.name = "Enter the full name";
  if (!/^\S+@\S+\.\S+$/.test(f.email.trim())) out.email = "Enter a work email";
  if (!["M", "F"].includes(f.gender)) out.gender = "Choose a gender";
  if (!COMPANY.company.departments.includes(f.department)) out.department = "Choose a department";
  if (!f.title.trim()) out.title = "Enter a designation";
  if (!GRADES.includes(f.grade)) out.grade = "Choose a grade";
  if (!stateOfCity(f.location)) out.location = "Choose a location";
  if (!/^2026-02-(0[1-9]|1\d|2[0-8])$/.test(f.joined)) out.joined = "This form adds February 2026 joiners: a date from 1 to 28 Feb 2026";
  const ctc = Number(f.annual_ctc);
  if (!Number.isInteger(ctc) || ctc < 120000) out.annual_ctc = "Enter the annual CTC in rupees";
  if (!["new", "old"].includes(f.tax_regime)) out.tax_regime = "Choose new or old";
  if (f.manager_id && !managers.includes(f.manager_id)) out.manager_id = "Choose a manager from the list";
  return out;
}

/** The employee the form describes, as BB-1057 (or the next id), joined in February. */
export function employeeFromForm(f: NewEmployeeForm, id: string): Employee {
  const ctc = Number(f.annual_ctc);
  const lta = ltaForGrade(f.grade);
  const st = structure(ctc, f.location, lta);
  return {
    id,
    name: f.name.trim(),
    gender: f.gender as "M" | "F",
    email: f.email.trim(),
    department: f.department,
    title: f.title.trim(),
    grade: f.grade,
    location: f.location,
    state: stateOfCity(f.location) ?? "",
    metro_for_hra: ["Mumbai", "New Delhi"].includes(f.location),
    joined: f.joined,
    manager_id: f.manager_id || null,
    status: "active",
    pan: "",
    uan: "",
    bank: "",
    tax_regime: f.tax_regime as Regime,
    regime_chosen_on: null,
    annual_ctc: ctc,
    structure: st,
    lta_monthly: lta,
    pf: true,
    esi: st.esi_applicable,
    first_fy_month: f.joined.slice(0, 7),
    ytd_to_jan: emptyYtd(),
    regime_comparison: { new_total: 0, old_total: 0, better: "new", saving: 0 },
    leave_balance: { EL: 0, CL: 0, SL: 0 },
  };
}

/** Days of February not yet joined: LOP for a joiner. */
export const joiningLop = (joined: string): number => Math.max(0, Number(joined.slice(8, 10)) - 1);

/** The prorated February payslip for a form that is complete enough to price. */
export function previewSlip(f: NewEmployeeForm): Slip | null {
  const ctc = Number(f.annual_ctc);
  if (!Number.isInteger(ctc) || ctc < 120000 || !stateOfCity(f.location) || !/^2026-02-\d\d$/.test(f.joined)) return null;
  const e = employeeFromForm({ ...f, gender: f.gender || "M", grade: f.grade || "G1", tax_regime: f.tax_regime || "new" }, "preview");
  return febSlip(e, joiningLop(f.joined), noDeclarations(), 0, emptyYtd());
}

// ------------------------------------------------------------ import

export type CsvRow = Record<string, string>;

/** RFC 4180, enough for a spreadsheet export: quoted fields with commas and "". */
export function parseCsv(text: string): { header: string[]; rows: CsvRow[] } {
  const lines: string[][] = [];
  let field = "";
  let row: string[] = [];
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]!;
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      field = "";
      if (row.some((c) => c !== "")) lines.push(row);
      row = [];
    } else field += ch;
  }
  if (field || row.length) {
    row.push(field);
    if (row.some((c) => c !== "")) lines.push(row);
  }
  const [header = [], ...rest] = lines;
  return { header, rows: rest.map((r) => Object.fromEntries(header.map((h, i) => [h, (r[i] ?? "").trim()]))) };
}

export const REQUIRED_COLUMNS = ["employee_id", "name", "email", "gender", "department", "designation", "location", "state", "date_of_joining", "annual_ctc", "pan", "tax_regime"];
const PAN = /^[A-Z]{5}\d{4}[A-Z]$/;

export interface ImportIssue {
  row: number;
  employee_id: string;
  problem: string;
}

export interface ImportResult {
  rows: CsvRow[];
  valid: number;
  issues: ImportIssue[];
  byLocation: [string, number][];
  regimes: { new: number; old: number };
}

/** The import step's validation: required fields, PAN format, duplicate ids, unknown managers. */
export function validateImport(rows: CsvRow[]): ImportResult {
  const issues: ImportIssue[] = [];
  const ids = new Set(rows.map((r) => r.employee_id).filter(Boolean));
  const seen = new Set<string>();
  const bad = new Set<number>();
  rows.forEach((r, i) => {
    const n = i + 2; // the header is line 1
    const flag = (problem: string) => {
      issues.push({ row: n, employee_id: r.employee_id || "—", problem });
      bad.add(i);
    };
    for (const col of REQUIRED_COLUMNS) if (!r[col]) flag(`${col.replace(/_/g, " ")} is empty`);
    if (r.pan && !PAN.test(r.pan)) flag(`PAN ${r.pan} is not in the AAAAA9999A format`);
    if (r.employee_id && seen.has(r.employee_id)) flag(`employee id ${r.employee_id} appears twice`);
    seen.add(r.employee_id);
    if (r.manager_id && !ids.has(r.manager_id)) flag(`manager ${r.manager_id} is not in the file`);
    if (r.tax_regime && !["new", "old"].includes(r.tax_regime)) flag(`tax regime "${r.tax_regime}" is not new or old`);
  });
  const loc = new Map<string, number>();
  for (const r of rows) loc.set(r.location, (loc.get(r.location) ?? 0) + 1);
  return {
    rows,
    valid: rows.length - bad.size,
    issues,
    byLocation: [...loc.entries()].sort((a, b) => b[1] - a[1]),
    regimes: { new: rows.filter((r) => r.tax_regime === "new").length, old: rows.filter((r) => r.tax_regime === "old").length },
  };
}

/**
 * The February 2026 test payroll over the imported rows, by the contract's
 * rule. The file carries the job and pay; history the file cannot (LTA by
 * grade, pay so far this year, verified declarations, leave and claims) comes
 * over from the previous payroll's records, matched by employee id.
 */
export function testPayroll(rows: CsvRow[]): { slips: Slip[]; totals: RunTotals; matched: number } {
  const slips: Slip[] = [];
  let matched = 0;
  const febSlips = COMPANY.payslips;
  for (const r of rows) {
    const prior = COMPANY.employees.find((e) => e.id === r.employee_id);
    if (prior) matched++;
    const e: Employee = {
      ...(prior ?? employeeFromForm({ ...emptyForm(), name: r.name, location: r.location, joined: r.date_of_joining, annual_ctc: r.annual_ctc }, r.employee_id)),
      annual_ctc: Number(r.annual_ctc),
      location: r.location,
      state: r.state,
      gender: r.gender as "M" | "F",
      tax_regime: r.tax_regime as Regime,
      joined: r.date_of_joining,
    };
    const lop = febSlips[e.id]?.find((s) => s.month === FEB)?.lop_days ?? 0;
    const decl = declOf(e.id, COMPANY.declarations);
    const reimb = reimbursementsFor(e.id, COMPANY.reimbursements.claims);
    slips.push(febSlip(e, lop, decl, reimb, prior?.ytd_to_jan ?? emptyYtd()));
  }
  return { slips, totals: totalsOf(slips), matched };
}
