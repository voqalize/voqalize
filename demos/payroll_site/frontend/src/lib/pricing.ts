/**
 * Paynora's price for a team: the plan and the per-employee maths, line by line.
 *
 * The page's twin of backend/pricing.py; both are held to
 * content/pricing_cases.json (pricing.test.ts here, the e2e on the brain's
 * side), so the calculator shows the number the agent says. The rule is
 * pricing_rules.plan_choice in data/product.json. Whole rupees, rounded half up.
 */
import { MODULES, PLAN_ORDER, PLANS, RULES, type PlanId } from "../data/product";
import { inr } from "./format";

export type Billing = "monthly" | "annual";

export interface PriceInput {
  headcount: number;
  modules: string[];
  billing: Billing;
  filing: boolean;
}

export interface Line {
  key: "base" | "minimum" | "filing" | "subtotal" | "discount" | "gst" | "total" | "annual" | "setup";
  label: string;
  amount: number;
  note: string;
}

export interface Quote {
  status: "ok" | "custom";
  headcount: number;
  modules: string[];
  billing: Billing;
  filing: boolean;
  plan: PlanId | "";
  plan_name: string;
  why: string[];
  rate: number;
  base: number;
  minimum: number;
  minimum_applies: boolean;
  subscription: number;
  filing_fee: number;
  monthly: number;
  discount: number;
  monthly_net: number;
  gst: number;
  monthly_total: number;
  setup_fee: number;
  setup_waived: boolean;
  setup_due: number;
  setup_gst: number;
  annual_net: number;
  annual_gst: number;
  annual_total: number;
  lines: Line[];
}

/** `percent` of `amount` in whole rupees, half up — the same integer maths as Python. */
export const pct = (amount: number, percent: number) => Math.floor((amount * percent * 100 + 5000) / 10000);

const FILING = RULES.addons.find((a) => a.id === "filing")!;
const rank = (plan: string) => PLAN_ORDER.indexOf(plan as PlanId);
const plan = (id: PlanId) => PLANS.find((p) => p.id === id)!;

export function choosePlan(headcount: number, modules: string[], filing: boolean): { plan: PlanId | null; why: string[] } {
  let need = 0;
  const why: string[] = [];
  for (const id of modules) {
    const m = MODULES.find((x) => x.id === id);
    if (!m) continue;
    const r = rank(m.min_plan);
    if (r > 0) why.push(`${m.name} needs ${plan(PLAN_ORDER[r]).name} or above`);
    need = Math.max(need, r);
  }
  if (filing) {
    const first = Math.min(...FILING.available_on.map(rank));
    why.push(`the filing service is on ${plan(PLAN_ORDER[first]).name} and above`);
    need = Math.max(need, first);
  }
  for (const id of PLAN_ORDER.slice(need)) {
    if (headcount <= plan(id).max_employees) {
      if (rank(id) > need) why.push(`${headcount} employees is above the ${plan(PLAN_ORDER[need]).name} limit`);
      return { plan: id, why };
    }
  }
  return { plan: null, why };
}

export function quote({ headcount, modules, billing, filing }: PriceInput): Quote {
  const mods = [...new Set(modules)].filter((m) => MODULES.some((x) => x.id === m));
  const q: Quote = {
    status: "ok", headcount, modules: mods, billing, filing, plan: "", plan_name: "", why: [],
    rate: 0, base: 0, minimum: 0, minimum_applies: false, subscription: 0, filing_fee: 0, monthly: 0,
    discount: 0, monthly_net: 0, gst: 0, monthly_total: 0, setup_fee: 0, setup_waived: false, setup_due: 0,
    setup_gst: 0, annual_net: 0, annual_gst: 0, annual_total: 0, lines: [],
  };
  const chosen = choosePlan(headcount, mods, filing);
  q.why = chosen.why;
  if (!chosen.plan) return { ...q, status: "custom" };
  const p = plan(chosen.plan);
  q.plan = chosen.plan;
  q.plan_name = p.name;
  q.rate = p.price_per_employee_month;
  q.base = headcount * q.rate;
  q.minimum = p.minimum_month;
  q.minimum_applies = q.base < q.minimum;
  q.subscription = Math.max(q.base, q.minimum);
  q.filing_fee = filing ? headcount * FILING.price_per_employee_month : 0;
  q.monthly = q.subscription + q.filing_fee;
  q.discount = billing === "annual" ? pct(q.monthly, RULES.annual_discount_pct) : 0;
  q.monthly_net = q.monthly - q.discount;
  q.gst = pct(q.monthly_net, RULES.gst_pct);
  q.monthly_total = q.monthly_net + q.gst;
  q.setup_fee = p.setup_fee;
  q.setup_waived = billing === "annual" && RULES.setup_fee_waived_on_annual && q.setup_fee > 0;
  q.setup_due = q.setup_waived ? 0 : q.setup_fee;
  q.setup_gst = pct(q.setup_due, RULES.gst_pct);
  q.annual_net = q.monthly_net * 12;
  q.annual_gst = pct(q.annual_net, RULES.gst_pct);
  q.annual_total = q.annual_net + q.annual_gst;
  q.lines = lines(q);
  return q;
}

function lines(q: Quote): Line[] {
  const out: Line[] = [
    { key: "base", label: `${q.headcount} employees × ${inr(q.rate)}`, amount: q.base, note: `${q.plan_name} plan` },
    {
      key: "minimum",
      label: `Plan minimum ${inr(q.minimum)}`,
      amount: q.subscription,
      note: q.minimum_applies ? "applies: your fee is the minimum" : "not applied: you are above it",
    },
  ];
  if (q.filing) {
    out.push({ key: "filing", label: `Filing service, ${q.headcount} × ${inr(FILING.price_per_employee_month)}`, amount: q.filing_fee, note: "add-on" });
  }
  out.push({ key: "subtotal", label: "Monthly fee", amount: q.monthly, note: "before GST" });
  if (q.billing === "annual") {
    out.push({ key: "discount", label: `Annual billing, ${RULES.annual_discount_pct}% off`, amount: -q.discount, note: `${inr(q.monthly_net)} a month` });
  }
  out.push({ key: "gst", label: `GST ${RULES.gst_pct}%`, amount: q.gst, note: "on the monthly fee" });
  out.push({ key: "total", label: "Monthly total with GST", amount: q.monthly_total, note: "" });
  if (q.billing === "annual") out.push({ key: "annual", label: "Billed yearly, with GST", amount: q.annual_total, note: "12 months" });
  out.push(
    q.setup_fee
      ? {
          key: "setup",
          label: "One-time setup fee",
          amount: q.setup_due,
          note: q.setup_waived ? "waived on annual billing" : `plus ${inr(q.setup_gst)} GST, waived if you pay annually`,
        }
      : { key: "setup", label: "One-time setup fee", amount: 0, note: "none on this plan" },
  );
  return out;
}
