/**
 * The ground truth this app starts from: data/company.json (the customer,
 * frozen at `today`) and data/product.json (Paynora itself), typed. Nothing
 * here changes; the session's mutable copy lives in the store (state/store.ts).
 */
import companyJson from "../../../data/company.json";
import productJson from "../../../data/product.json";
import type { Declarations, Payslip, Regime, Structure, Ytd } from "./engine";

export interface Employee {
  id: string;
  name: string;
  gender: "M" | "F";
  email: string;
  department: string;
  title: string;
  grade: string;
  location: string;
  state: string;
  metro_for_hra: boolean;
  joined: string;
  manager_id: string | null;
  status: string;
  pan: string;
  uan: string;
  bank: string;
  tax_regime: Regime;
  regime_chosen_on: string | null;
  annual_ctc: number;
  structure: Structure;
  lta_monthly: number;
  pf: boolean;
  esi: boolean;
  first_fy_month: string;
  ytd_to_jan: Ytd;
  regime_comparison: { new_total: number; old_total: number; better: Regime; saving: number };
  leave_balance: Record<"EL" | "CL" | "SL", number>;
}

export interface Slip extends Payslip {
  month: string;
  regime: Regime;
  joining_days_unpaid: number;
}

export interface PayrollRun {
  id: string;
  month: string;
  label: string;
  status: "paid" | "draft" | "approved";
  pay_date: string;
  days: number;
  approved_by: string | null;
  employer_cost: number;
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
}

export type LeaveType = "EL" | "CL" | "SL" | "LOP";
export interface LeaveRequest {
  id: string;
  employee_id: string;
  type: LeaveType;
  from: string;
  to: string;
  days: number;
  status: "approved" | "pending" | "rejected";
  reason: string;
  applied_on: string;
  approver_id: string;
  /** Set by this app when it approves one: the days that became loss of pay. */
  lop_days?: number;
}

export interface Claim {
  id: string;
  employee_id: string;
  category: string;
  amount: number;
  bill_amount: number;
  date: string;
  status: "paid" | "approved" | "needs_fix" | "pending" | "rejected";
  description: string;
  payroll_month: string;
  note: string | null;
  bill_file: string;
}

export interface DeclarationItem {
  section: string;
  label: string;
  declared: number;
  verified: number;
  proof_status: "verified" | "not_submitted" | "partly_verified" | "submitted";
  rent_monthly?: number;
  landlord_pan?: string;
}

export interface Declaration {
  employee_id: string;
  regime: Regime;
  declared_on: string;
  proofs_submitted_on: string | null;
  proofs_verified_on: string | null;
  items: DeclarationItem[];
  declared_80c_other: number;
  verified_80c_other: number;
  engine: { declared: Declarations; verified: Declarations };
}

export interface Ticket {
  id: string;
  subject: string;
  status: "resolved" | "open";
  opened: string;
  summary: string;
  employee_id?: string | null;
  /** A support request or a feature request (raised in this session; the sample tickets have none). */
  kind?: "support" | "feature";
}

export interface Company {
  today: string;
  fy: string;
  company: {
    name: string;
    legal_name: string;
    industry: string;
    founded: number;
    registered_office: string;
    pan: string;
    tan: string;
    pf_code: string;
    esi_code: string;
    pt_registrations: Record<string, string>;
    plan: string;
    plan_note: string;
    admin: { employee_id: string; name: string; role: string };
    payroll_approver: { employee_id: string; name: string };
    pay_cycle: string;
    locations: { city: string; state: string; office: string }[];
    departments: string[];
    regime_change_policy: string;
    windows: {
      declaration: { opens: string; closes: string };
      proofs: { opens: string; first_verification: string; closes: string };
    };
  };
  structure_rule: string;
  employees: Employee[];
  payslips: Record<string, Slip[]>;
  payroll_runs: PayrollRun[];
  leave: {
    policy: {
      year: string;
      types: { id: LeaveType; name: string; per_year: number | null; accrual: string; carry_forward_max: number; encashable: boolean }[];
      approval: string;
      lop_rule: string;
      attendance_cutoff: string;
      sandwich_rule: boolean;
    };
    holidays: { date: string; name: string; locations: string[] }[];
    requests: LeaveRequest[];
  };
  reimbursements: {
    policy: { category: string; monthly_limit: number | null; grades: string; taxable: boolean; bill_required: boolean }[];
    claims: Claim[];
  };
  declarations: Declaration[];
  form16: Record<string, { status: string; issued_on?: string; due_by?: string; note: string }>;
  tickets: Ticket[];
  stories: {
    ravi_net_drop: { employee_id: string; why_tds: string; [k: string]: unknown };
    kavitha_old_better: { employee_id: string; new_total: number; old_total: number; better: Regime; saving: number };
  };
}

export const COMPANY = companyJson as unknown as Company;
export const PRODUCT = productJson;
export const TODAY = COMPANY.today;
export const DRAFT_RUN_ID = "PR-2026-02";
export const DRAFT_MONTH = "2026-02";
/** Months with per-employee payslips in company.json. */
export const SLIP_MONTHS = ["2025-11", "2025-12", "2026-01", "2026-02"];
export const ADMIN = COMPANY.company.admin;
export const DISCLAIMER = "Illustrative, FY 2025-26";
