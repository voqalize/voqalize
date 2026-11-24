/**
 * The three public forms (CONTRACT.md "Forms"): open_account (six steps),
 * card_apply and loan_apply (one page each). One store, the same for a tap and
 * for the agent's `form.fill`: field names are the contract, values are kept as
 * strings exactly as the form shows them (choice ids, YYYY-MM-DD, digits).
 *
 * Every change is reported to the brain as `form_changed` (names only, never
 * values), debounced, and every submit as `form_submitted`.
 */
import { create } from "zustand";
import { creditCardProduct, customer, loanProduct, products } from "../data/bank";
import { type Eligibility, emi, loanEligibility } from "../lib/bankmath";
import { type By, currentBy, emit } from "../voice/events";

export type FormId = "open_account" | "card_apply" | "loan_apply";
export const FORM_IDS: FormId[] = ["open_account", "card_apply", "loan_apply"];

type Kind = "text" | "date" | "choice" | "number" | "digits";

export interface FieldDef {
  name: string;
  label: string;
  kind: Kind;
  hint?: string;
  placeholder?: string;
  /** Required (for loan_apply, `when` narrows it to some loan types). */
  optional?: boolean;
}

// ─── Labels for choice values ───────────────────────────────────────────────

const CHOICE_LABELS: Record<string, string> = {
  female: "Female",
  male: "Male",
  other: "Other",
  owned: "Owned",
  rented: "Rented",
  family: "Family home",
  company: "Company provided",
  salaried: "Salaried",
  self_employed: "Self-employed",
  business: "Business owner",
  student: "Student",
  homemaker: "Homemaker",
  retired: "Retired",
  below_5l: "Below ₹5 lakh",
  "5l_10l": "₹5–10 lakh",
  "10l_25l": "₹10–25 lakh",
  "25l_50l": "₹25–50 lakh",
  above_50l: "Above ₹50 lakh",
  spouse: "Spouse",
  father: "Father",
  mother: "Mother",
  son: "Son",
  daughter: "Daughter",
  brother: "Brother",
  sister: "Sister",
  yes: "Yes",
  no: "No",
  morning: "Morning, 9–12",
  afternoon: "Afternoon, 12–4",
  evening: "Evening, 4–8",
  home: "Home loan",
  personal: "Personal loan",
  gold: "Gold loan",
  car: "Car loan",
};

export function choiceLabel(field: string, value: string): string {
  if (field === "variant") return products.savings_variants.find((v) => v.id === value)?.name ?? value;
  if (field === "card_id") return creditCardProduct(value)?.name ?? value;
  if (field === "nominee_relation" && value === "other") return "Someone else";
  return CHOICE_LABELS[value] ?? value;
}

/** The values a choice field takes, or null for a free field. */
export function choicesOf(form: FormId, field: string): string[] | null {
  if (form === "open_account") return products.account_opening.choices[field] ?? null;
  if (form === "card_apply") {
    if (field === "card_id") return products.credit_cards.map((c) => c.id);
    return products.card_application.choices[field] ?? null;
  }
  return products.loan_application.choices[field] ?? null;
}

// ─── Field definitions ──────────────────────────────────────────────────────

const F = (name: string, label: string, kind: Kind, extra: Partial<FieldDef> = {}): FieldDef => ({ name, label, kind, ...extra });

export const FIELDS: Record<FormId, FieldDef[]> = {
  open_account: [
    F("full_name", "Full name, as on your PAN", "text", { placeholder: "Priya Raghavan" }),
    F("date_of_birth", "Date of birth", "date"),
    F("gender", "Gender", "choice"),
    F("mobile", "Mobile number", "digits", { placeholder: "98765 43210", hint: "10 digits. We send a one-time code here." }),
    F("email", "Email", "text", { placeholder: "priya@example.com" }),
    F("address_line", "House, street and area", "text", { placeholder: "Flat 4B, Lakeview Apartments, 12th Main, Indiranagar" }),
    F("city", "City", "text", { placeholder: "Bengaluru" }),
    F("state", "State", "text", { placeholder: "Karnataka" }),
    F("pincode", "PIN code", "digits", { placeholder: "560038" }),
    F("residence_type", "This home is", "choice"),
    F("pan", "PAN", "text", { placeholder: "ABCDE1234F", hint: "Sample format ABCDE1234F. Shown masked once entered." }),
    F("aadhaar", "Aadhaar number", "digits", { placeholder: "1234 5678 9012", hint: "12 digits, sample value. Shown masked once entered." }),
    F("occupation", "Occupation", "choice"),
    F("annual_income", "Annual income", "choice"),
    F("nominee_name", "Nominee's full name", "text", { placeholder: "Ravi Raghavan" }),
    F("nominee_relation", "Relationship to you", "choice"),
    F("nominee_dob", "Nominee's date of birth", "date"),
    F("variant", "Savings account", "choice"),
    F("debit_card", "Debit card", "choice"),
    F("cheque_book", "Cheque book", "choice"),
  ],
  card_apply: [
    F("card_id", "Card", "choice"),
    F("full_name", "Full name, as on your PAN", "text", { placeholder: "Priya Raghavan" }),
    F("mobile", "Mobile number", "digits", { placeholder: "98765 43210" }),
    F("pan", "PAN", "text", { placeholder: "ABCDE1234F", hint: "Sample format ABCDE1234F. Shown masked." }),
    F("employment", "Employment", "choice"),
    F("monthly_income", "Monthly take-home income (₹)", "number", { placeholder: "85000" }),
    F("city", "City", "text", { placeholder: "Pune" }),
  ],
  loan_apply: [
    F("loan_type", "Loan", "choice"),
    F("full_name", "Full name", "text", { placeholder: "Priya Raghavan" }),
    F("mobile", "Mobile number", "digits", { placeholder: "98765 43210" }),
    F("city", "City", "text", { placeholder: "Chennai" }),
    F("employment", "Employment", "choice"),
    F("employer", "Employer or business name", "text", { placeholder: "Sundaram Textiles Pvt Ltd" }),
    F("monthly_income", "Monthly take-home income (₹)", "number", { placeholder: "90000" }),
    F("existing_emis", "EMIs you already pay each month (₹)", "number", { placeholder: "0", optional: true, hint: "Leave at 0 if none." }),
    F("amount", "Loan amount (₹)", "number"),
    F("tenure_months", "Tenure (months)", "number"),
    F("property_value", "Property value (₹)", "number"),
    F("gold_grams", "Gold to pledge (grams, 22 carat)", "number"),
    F("car_price", "On-road price of the car (₹)", "number"),
    F("preferred_time", "Best time for our call", "choice"),
  ],
};

export const fieldDef = (form: FormId, name: string) => FIELDS[form].find((f) => f.name === name);

/** open_account's steps, from products.json. */
export const OA_STEPS = products.account_opening.steps;
export const stepOfField = (field: string): number => OA_STEPS.find((s) => s.fields.includes(field))?.n ?? 1;

/** Which loan_apply fields apply to a loan type. */
export function loanFieldsFor(type: string | undefined): string[] {
  const all = FIELDS.loan_apply.map((f) => f.name);
  return all.filter((f) => {
    if (f === "property_value") return type === "home";
    if (f === "gold_grams") return type === "gold";
    if (f === "car_price") return type === "car";
    return true;
  });
}

/** The fields of a form (or of one open_account step) that apply now. */
export function fieldsOf(form: FormId, values: Record<string, string>, step?: number): string[] {
  if (form === "open_account") {
    if (step != null) return OA_STEPS.find((s) => s.n === step)?.fields ?? [];
    return OA_STEPS.flatMap((s) => s.fields);
  }
  if (form === "loan_apply") return loanFieldsFor(values.loan_type);
  return FIELDS[form].map((f) => f.name);
}

// ─── Validation ─────────────────────────────────────────────────────────────

const digitsOnly = (s: string) => s.replace(/[\s-]/g, "");

/** Normalise a value the way the form keeps it (mobile without +91, PAN upper case…). */
export function normalise(form: FormId, field: string, raw: string): string {
  const v = String(raw ?? "").trim();
  if (field === "mobile") return digitsOnly(v).replace(/^(\+?91)(?=\d{10}$)/, "").replace(/^0(?=\d{10}$)/, "");
  if (field === "aadhaar" || field === "pincode") return digitsOnly(v);
  if (field === "pan") return v.toUpperCase().replace(/\s/g, "");
  const def = fieldDef(form, field);
  if (def?.kind === "number") return v.replace(/[₹,\s]/g, "");
  if (def?.kind === "choice") return v.toLowerCase();
  return v;
}

function validDate(s: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const d = new Date(`${s}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  const [y, m, dd] = s.split("-").map(Number);
  if (d.getFullYear() !== y || d.getMonth() + 1 !== m || d.getDate() !== dd) return null;
  return d;
}
const ageOn = (d: Date) => {
  const t = new Date();
  let a = t.getFullYear() - d.getFullYear();
  if (t.getMonth() < d.getMonth() || (t.getMonth() === d.getMonth() && t.getDate() < d.getDate())) a -= 1;
  return a;
};

/** Why `value` cannot go in `field`, or null when it can. `value` is normalised. */
export function invalid(form: FormId, field: string, value: string, values: Record<string, string> = {}): string | null {
  if (value === "") return null;
  const choices = choicesOf(form, field);
  if (choices) return choices.includes(value) ? null : `${fieldDef(form, field)?.label ?? field} is one of: ${choices.join(", ")}`;
  switch (field) {
    case "mobile":
      return /^[6-9]\d{9}$/.test(value) ? null : "a mobile number is 10 digits starting with 6, 7, 8 or 9";
    case "email":
      return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value) ? null : "that is not an email address";
    case "pincode":
      return /^[1-9]\d{5}$/.test(value) ? null : "a PIN code is 6 digits and does not start with 0";
    case "pan":
      return /^[A-Z]{5}\d{4}[A-Z]$/.test(value) ? null : "a PAN is five letters, four digits and a letter, like ABCDE1234F";
    case "aadhaar":
      return /^[2-9]\d{11}$/.test(value) ? null : "an Aadhaar number is 12 digits and does not start with 0 or 1";
    case "date_of_birth": {
      const d = validDate(value);
      if (!d) return "a date is written YYYY-MM-DD, like 1992-08-14";
      const a = ageOn(d);
      if (a < 18) return "the account holder must be 18 or older for this account";
      if (a > 100) return "that date of birth is more than 100 years ago";
      return null;
    }
    case "nominee_dob": {
      const d = validDate(value);
      if (!d) return "a date is written YYYY-MM-DD, like 1990-01-31";
      if (d.getTime() > Date.now()) return "the nominee's date of birth cannot be in the future";
      return null;
    }
    case "full_name":
    case "nominee_name":
      return /^[\p{L} .'-]{2,}$/u.test(value) ? null : "a name is letters and spaces only";
  }
  if (fieldDef(form, field)?.kind === "number") {
    const n = Number(value);
    if (!Number.isFinite(n) || n < 0) return "that is not an amount";
    if (form === "loan_apply") {
      const loan = loanProduct(values.loan_type ?? "");
      if (loan && field === "amount" && (n < loan.amount_min || n > loan.amount_max))
        return `a ${loan.short.toLowerCase()} is ₹${loan.amount_min.toLocaleString("en-IN")} to ₹${loan.amount_max.toLocaleString("en-IN")}`;
      if (loan && field === "tenure_months" && (n < loan.tenure_min_months || n > loan.tenure_max_months || !Number.isInteger(n)))
        return `a ${loan.short.toLowerCase()} runs ${loan.tenure_min_months} to ${loan.tenure_max_months} months`;
    }
    if ((field === "monthly_income" || field === "amount" || field === "gold_grams") && n <= 0) return "enter an amount above zero";
  }
  return null;
}

// ─── Store ──────────────────────────────────────────────────────────────────

export interface Submission {
  reference: string;
  summary: string;
  at: number;
  values: Record<string, string>;
  lead?: Lead;
}

export interface Lead {
  id: string;
  loan_type: string;
  product: string;
  amount: number;
  tenure_months: number;
  rate: number;
  emi: number;
  eligibility: Eligibility;
  within: boolean;
  documents: string[];
  callback: string;
  city: string;
  team: string;
}

interface FormsState {
  values: Record<FormId, Record<string, string>>;
  step: Record<FormId, number>;
  reached: Record<FormId, number>;
  /** Errors on screen after a Continue / Submit press. */
  errors: Record<FormId, Record<string, string>>;
  submitted: Record<FormId, Submission | null>;
  setField: (form: FormId, field: string, value: string) => void;
  setStep: (form: FormId, step: number) => void;
  showErrors: (form: FormId, fields: string[]) => boolean;
  /** Required fields still empty or invalid (in one step for open_account). */
  missing: (form: FormId, step?: number) => string[];
  submit: (form: FormId) => Submission | { missing: string[] };
  reset: (form: FormId) => void;
}

const empty = () => ({ open_account: {}, card_apply: {}, loan_apply: {} }) as Record<FormId, Record<string, string>>;

const digits6 = () => String(Math.floor(100000 + Math.random() * 900000));

function required(form: FormId, values: Record<string, string>, step?: number): string[] {
  return fieldsOf(form, values, step).filter((f) => !fieldDef(form, f)?.optional);
}

function missingOf(form: FormId, values: Record<string, string>, step?: number): string[] {
  return required(form, values, step).filter((f) => !values[f] || invalid(form, f, values[f], values) !== null);
}

function buildLead(v: Record<string, string>): Lead {
  const loan = loanProduct(v.loan_type)!;
  const amount = Number(v.amount);
  const n = Number(v.tenure_months);
  const el = loanEligibility(loan, {
    monthly_income: Number(v.monthly_income) || 0,
    existing_emis: Number(v.existing_emis) || 0,
    tenure_months: n,
    gold_grams: Number(v.gold_grams) || 0,
  });
  return {
    id: `GLB-LD-${digits6()}`,
    loan_type: loan.id,
    product: loan.name,
    amount,
    tenure_months: n,
    rate: loan.rate_typical,
    emi: Math.round(emi(amount, loan.rate_typical, n)),
    eligibility: el,
    within: amount <= el.max_amount,
    documents: loan.documents,
    callback: choiceLabel("preferred_time", v.preferred_time),
    city: v.city,
    team: `${loan.short.toLowerCase()} team, ${v.city}`,
  };
}

function summarise(form: FormId, v: Record<string, string>, lead?: Lead): string {
  if (form === "open_account") return `${choiceLabel("variant", v.variant)} for ${v.full_name}; debit card ${v.debit_card}, cheque book ${v.cheque_book}`;
  if (form === "card_apply") return `${choiceLabel("card_id", v.card_id)} for ${v.full_name}, ${v.city}`;
  if (!lead) return "";
  return `${lead.product}, ₹${lead.amount.toLocaleString("en-IN")} over ${lead.tenure_months} months, EMI ₹${lead.emi.toLocaleString("en-IN")}; ${lead.within ? "within" : "above"} the eligible ₹${lead.eligibility.max_amount.toLocaleString("en-IN")}; callback ${v.preferred_time}`;
}

export const useForms = create<FormsState>((set, get) => ({
  values: empty(),
  step: { open_account: 1, card_apply: 1, loan_apply: 1 },
  reached: { open_account: 1, card_apply: 1, loan_apply: 1 },
  errors: { open_account: {}, card_apply: {}, loan_apply: {} },
  submitted: { open_account: null, card_apply: null, loan_apply: null },

  setField: (form, field, value) => {
    const v = normalise(form, field, value);
    const s = get();
    const errs = { ...s.errors[form] };
    delete errs[field];
    set({
      values: { ...s.values, [form]: { ...s.values[form], [field]: v } },
      errors: { ...s.errors, [form]: errs },
      submitted: s.submitted[form] ? { ...s.submitted, [form]: null } : s.submitted,
    });
    changed(form);
  },

  setStep: (form, step) => {
    const s = get();
    set({ step: { ...s.step, [form]: step }, reached: { ...s.reached, [form]: Math.max(s.reached[form], step) } });
    changed(form);
  },

  showErrors: (form, fields) => {
    const s = get();
    const values = s.values[form];
    const errs: Record<string, string> = {};
    for (const f of fields) {
      const v = values[f] ?? "";
      if (!v) {
        if (!fieldDef(form, f)?.optional) errs[f] = "Required";
      } else {
        const why = invalid(form, f, v, values);
        if (why) errs[f] = why.charAt(0).toUpperCase() + why.slice(1);
      }
    }
    set({ errors: { ...s.errors, [form]: errs } });
    return Object.keys(errs).length === 0;
  },

  missing: (form, step) => missingOf(form, get().values[form], step),

  submit: (form) => {
    const s = get();
    const values = s.values[form];
    const miss = missingOf(form, values);
    if (miss.length) {
      s.showErrors(form, fieldsOf(form, values));
      return { missing: miss };
    }
    const lead = form === "loan_apply" ? buildLead(values) : undefined;
    const prefix = form === "open_account" ? "GLB-SB-" : form === "card_apply" ? "GLB-CC-" : "";
    const reference = lead ? lead.id : `${prefix}${digits6()}`;
    const sub: Submission = { reference, summary: summarise(form, values, lead), at: Date.now(), values: { ...values }, lead };
    set({ submitted: { ...s.submitted, [form]: sub } });
    emit("form_submitted", { form, reference, summary: sub.summary });
    return sub;
  },

  reset: (form) => {
    const s = get();
    set({
      values: { ...s.values, [form]: {} },
      step: { ...s.step, [form]: 1 },
      reached: { ...s.reached, [form]: 1 },
      errors: { ...s.errors, [form]: {} },
      submitted: { ...s.submitted, [form]: null },
    });
  },
}));

// ─── form_changed, debounced, names only ────────────────────────────────────

const timers: Partial<Record<FormId, ReturnType<typeof setTimeout>>> = {};
const lastBy: Partial<Record<FormId, By>> = {};

function changed(form: FormId) {
  // Who made the change is decided now, not when the timer fires.
  const by = currentBy();
  lastBy[form] = lastBy[form] === "agent" ? "agent" : by;
  clearTimeout(timers[form]);
  timers[form] = setTimeout(() => {
    const s = useForms.getState();
    const values = s.values[form];
    const all = fieldsOf(form, values);
    const filled = all.filter((f) => !!values[f]);
    const missing = missingOf(form, values);
    emit("form_changed", { form, step: s.step[form], filled, missing }, lastBy[form] ?? by);
    delete lastBy[form];
  }, 600);
}

// ─── Display helpers ────────────────────────────────────────────────────────

/** ABCDE1234F → ABC•••••4F */
export const maskPan = (p: string) => (p.length === 10 ? `${p.slice(0, 3)}•••••${p.slice(8)}` : p);
/** 123456789012 → XXXX XXXX 9012 */
export const maskAadhaar = (a: string) => (a.length === 12 ? `XXXX XXXX ${a.slice(8)}` : a);

/** What a field shows on review screens. */
export function display(form: FormId, field: string, value: string): string {
  if (!value) return "—";
  if (field === "pan") return maskPan(value);
  if (field === "aadhaar") return maskAadhaar(value);
  if (choicesOf(form, field)) return choiceLabel(field, value);
  if (field === "date_of_birth" || field === "nominee_dob") {
    const d = validDate(value);
    if (d) return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  }
  if (field === "mobile" && value.length === 10) return `+91 ${value.slice(0, 5)} ${value.slice(5)}`;
  if (fieldDef(form, field)?.kind === "number" && field !== "tenure_months" && field !== "gold_grams") {
    const n = Number(value);
    if (Number.isFinite(n)) return `₹${n.toLocaleString("en-IN")}`;
  }
  if (field === "tenure_months") return `${value} months`;
  if (field === "gold_grams") return `${value} g`;
  return value;
}

/** The signed-in customer's details, for "Fill from my profile". */
export function profileFill(form: FormId): Record<string, string> {
  const p = customer.profile;
  const out: Record<string, string> = { full_name: p.name, city: p.city, monthly_income: String(p.monthly_income), employment: "salaried" };
  if (form === "loan_apply") {
    out.employer = p.employer;
    out.existing_emis = String(customer.loans.reduce((a, l) => a + l.emi, 0));
  }
  return out;
}
