export type ProductId = "car" | "bike" | "health" | "term" | "home" | "travel";

export interface Option {
  value: string;
  label: string;
}

export interface QuoteField {
  id: string;
  label: string;
  type: "select" | "integer" | "money" | "text";
  ask?: string;
  options?: Option[];
  options_from?: "cities";
  optional?: boolean;
  default?: string;
  min?: number;
  max?: number;
}

export interface AddonSpec {
  id: string;
  label: string;
  default?: boolean;
  price: Record<string, unknown>;
  max_age?: number;
  min_ncb?: number;
  requires?: string;
}

export interface Product {
  id: ProductId;
  name: string;
  plan: string;
  gst_percent: number;
  gst_note?: string;
  fields: QuoteField[];
  addons: AddonSpec[];
  tables: Record<string, any>;
  method: string[];
}

export interface City {
  value: string;
  label: string;
  zone: string;
}

export interface ProductsFile {
  rating_year: number;
  cities: City[];
  ncb: { by_years: number[] };
  products: Product[];
}

export type ShowIf = Record<string, string[]>;

export interface ClaimField {
  id: string;
  label: string;
  type: "select" | "text" | "textarea" | "date" | "time" | "money";
  options?: Option[];
  options_from?: "policies" | "members" | "garages" | "hospitals";
  show_if?: ShowIf;
  optional?: boolean;
  prefill?: string;
  pattern?: string;
}

export interface ClaimSection {
  id: string;
  title: string;
  types: string[];
  note?: string;
  fields: ClaimField[];
}

export interface ClaimDocument {
  id: string;
  label: string;
  types: string[];
  optional?: boolean;
  show_if?: ShowIf;
}

export interface ClaimForm {
  types: { id: "motor" | "health"; label: string; hint: string; products: ProductId[] }[];
  sections: ClaimSection[];
  documents: ClaimDocument[];
  review: { declaration: string; reference_format: string };
}

export interface Customer {
  id: string;
  name: string;
  first_name: string;
  dob: string;
  phone: string;
  email: string;
  address: string;
  city: string;
  family: { id: string; name: string; relation: string; dob: string }[];
  bank_on_file: { account_holder: string; bank_name: string; account_number: string; masked: string; ifsc: string };
  policies: string[];
  past_claims: { reference: string; policy_id: string; summary: string; status: string; amount: number; date: string }[];
}

export type ClauseKind = "covered" | "excluded" | "limit" | "waiting" | "copay" | "deductible" | "condition" | "info";

export interface Clause {
  id: string;
  title: string;
  kind: ClauseKind;
  text: string;
  plain?: string;
  tags?: string[];
}

export interface PolicySection {
  id: string;
  number: string;
  title: string;
  clauses: Clause[];
}

export interface PolicyDoc {
  id: string;
  product: ProductId;
  title: string;
  plan: string;
  policy_number: string;
  status: "active" | "upcoming" | string;
  start: string;
  end: string;
  premium_paid: number;
  summary: string;
  insured: { id: string; name: string; role: string }[];
  schedule: { label: string; value: string }[];
  addons: { id: string; label: string; included: boolean }[];
  sections: PolicySection[];
}

export interface NetworkPlace {
  id: string;
  name: string;
  area: string;
  city: string;
  cashless?: boolean;
  brands?: string;
}

export interface Network {
  garages: NetworkPlace[];
  hospitals: NetworkPlace[];
}

/** content/products.json, read loosely: every part is optional. */
export interface ProductContent {
  id?: string;
  hero?: { title?: string; headline?: string; subtitle?: string; sub?: string; lede?: string } | string;
  tagline?: string;
  name?: string;
  headline?: string;
  subhead?: string;
  starting_from_note?: string;
  highlights?: (string | { title?: string; text?: string; body?: string })[];
  covered?: (string | { title?: string; text?: string })[];
  not_covered?: (string | { title?: string; text?: string })[];
  addons?: Record<string, string | { title?: string; text?: string; body?: string }> | { id: string; text?: string; body?: string; title?: string }[];
  addon_explainers?: Record<string, string | { title?: string; text?: string }> | { id: string; text?: string; title?: string }[];
  faqs?: { q?: string; a?: string; question?: string; answer?: string }[];
}

export interface ClaimsGuide {
  helpline?: string;
  helpline_note?: string;
  motor?: { next_steps?: string[]; turnaround?: string; [k: string]: unknown };
  health?: {
    cashless?: { next_steps?: string[]; turnaround?: string };
    reimbursement?: { next_steps?: string[]; turnaround?: string };
    [k: string]: unknown;
  };
  [k: string]: unknown;
}
