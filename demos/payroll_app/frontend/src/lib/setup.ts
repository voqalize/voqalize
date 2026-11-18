/**
 * The setup wizard's steps and fields, named exactly as `setup.fill` names
 * them in scene.json. Every field starts empty; "Use details from signup"
 * fills each from company.json (`signup`).
 */
import { COMPANY } from "./data";

export const SETUP_STEPS = ["company", "structure", "import", "leave", "test_run", "done"] as const;
export type SetupStep = (typeof SETUP_STEPS)[number];

export const STEP_TITLES: Record<SetupStep, string> = {
  company: "Company details",
  structure: "Pay structure",
  import: "Import employees",
  leave: "Leave policy",
  test_run: "Test payroll",
  done: "Done",
};

export interface SetupField {
  name: string;
  step: SetupStep;
  label: string;
  hint?: string;
  kind: "text" | "number" | "select" | "textarea";
  options?: string[];
  /** Rupees, a percentage or days: shown beside the input. */
  unit?: string;
  signup: string;
  /** Checks a value; returns why it is wrong, or null. */
  check?: (v: string) => string | null;
}

const c = COMPANY.company;
const policy = COMPANY.leave.policy;
const type = (id: string) => policy.types.find((t) => t.id === id)!;
const pct = (v: string) => (/^\d{1,2}(\.\d+)?$/.test(v) && Number(v) <= 100 ? null : "a percentage from 0 to 100");
const whole = (v: string) => (/^\d+$/.test(v) ? null : "a whole number");

export const SETUP_FIELDS: SetupField[] = [
  { name: "company_name", step: "company", label: "Company name", kind: "text", signup: c.name },
  { name: "legal_name", step: "company", label: "Legal name", hint: "As on the certificate of incorporation", kind: "text", signup: c.legal_name },
  {
    name: "pan",
    step: "company",
    label: "Company PAN",
    kind: "text",
    signup: c.pan,
    check: (v) => (/^[A-Z]{5}\d{4}[A-Z]$/.test(v.toUpperCase()) ? null : "ten characters, like AAKCB7713Q"),
  },
  {
    name: "tan",
    step: "company",
    label: "TAN",
    hint: "For TDS returns",
    kind: "text",
    signup: c.tan,
    check: (v) => (/^[A-Z]{4}\d{5}[A-Z]$/.test(v.toUpperCase()) ? null : "ten characters, like BLRB09412E"),
  },
  { name: "registered_office", step: "company", label: "Registered office", kind: "textarea", signup: c.registered_office },
  { name: "pf_code", step: "company", label: "PF establishment code", kind: "text", signup: c.pf_code },
  { name: "esi_code", step: "company", label: "ESI code", kind: "text", signup: c.esi_code },
  { name: "pt_karnataka", step: "company", label: "PT registration, Karnataka", kind: "text", signup: c.pt_registrations.Karnataka ?? "" },
  { name: "pt_maharashtra", step: "company", label: "PT registration, Maharashtra", kind: "text", signup: c.pt_registrations.Maharashtra ?? "" },
  {
    name: "pay_cycle",
    step: "company",
    label: "Pay cycle",
    kind: "select",
    options: ["Calendar month; salary paid on the last working day", "Calendar month; salary paid on the 1st of the next month", "26th to 25th; salary paid on the last working day"],
    signup: c.pay_cycle,
  },
  { name: "basic_pct", step: "structure", label: "Basic", hint: "Of monthly CTC", kind: "number", unit: "%", signup: "40", check: pct },
  { name: "hra_metro_pct", step: "structure", label: "HRA in Mumbai and New Delhi", hint: "Of basic", kind: "number", unit: "%", signup: "50", check: pct },
  { name: "hra_non_metro_pct", step: "structure", label: "HRA elsewhere", hint: "Of basic", kind: "number", unit: "%", signup: "40", check: pct },
  { name: "lta_g5", step: "structure", label: "LTA for grade G5", hint: "A month", kind: "number", unit: "₹", signup: "3000", check: whole },
  { name: "lta_g6_up", step: "structure", label: "LTA for G6 and up", hint: "A month", kind: "number", unit: "₹", signup: "5000", check: whole },
  { name: "pf_rule", step: "structure", label: "Provident fund", kind: "text", signup: "12% of basic up to ₹15,000" },
  { name: "esi_rule", step: "structure", label: "ESI", kind: "text", signup: "Employer 3.25% when gross is up to ₹21,000" },
  { name: "el_per_year", step: "leave", label: "Earned leave a year", kind: "number", unit: "days", signup: String(type("EL").per_year), check: whole },
  { name: "cl_per_year", step: "leave", label: "Casual leave a year", kind: "number", unit: "days", signup: String(type("CL").per_year), check: whole },
  { name: "sl_per_year", step: "leave", label: "Sick leave a year", kind: "number", unit: "days", signup: String(type("SL").per_year), check: whole },
  { name: "el_carry_forward", step: "leave", label: "Earned leave carried forward, at most", kind: "number", unit: "days", signup: String(type("EL").carry_forward_max), check: whole },
  { name: "attendance_cutoff", step: "leave", label: "Attendance cut-off", hint: "When an approved leave counts in payroll", kind: "textarea", signup: policy.attendance_cutoff },
  { name: "lop_rule", step: "leave", label: "Loss of pay", kind: "textarea", signup: policy.lop_rule },
];

export const fieldsOf = (step: SetupStep) => SETUP_FIELDS.filter((f) => f.step === step);
export const setupField = (name: string) => SETUP_FIELDS.find((f) => f.name === name) ?? null;
export const emptySetupFields = (): Record<string, string> => Object.fromEntries(SETUP_FIELDS.map((f) => [f.name, ""]));
