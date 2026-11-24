/**
 * The bank's arithmetic, written once for the page. The brain has the same
 * functions in `backend/bankmath.py`, and `src/lib/bankmath.test.ts` pins both
 * to the same numbers (CONTRACT.md, "Maths"). The agent says the brain's
 * numbers; the page shows these; they must agree to the rupee.
 */
import { type CreditCardProduct, type LoanProduct, customer, products } from "../data/bank";

/** Reducing-balance EMI. */
export function emi(principal: number, ratePa: number, months: number): number {
  if (principal <= 0 || months <= 0) return 0;
  const r = ratePa / 12 / 100;
  if (r === 0) return principal / months;
  const f = Math.pow(1 + r, months);
  return (principal * r * f) / (f - 1);
}

export interface EmiRow {
  months: number;
  rate: number;
  emi: number;
  total_interest: number;
  processing_fee: number;
  gst_on_fee: number;
  total_cost: number;
}

/** A card spend converted to EMI, for one tenure (products.emi). */
export function cardEmi(amount: number, months: number): EmiRow {
  const t = products.emi.tenures.find((x) => x.months === months);
  const rate = t?.rate ?? 0;
  const m = Math.round(emi(amount, rate, months));
  const interest = Math.round(m * months - amount);
  const fee = Math.round(Math.max(products.emi.processing_fee_min, (amount * products.emi.processing_fee_pct) / 100));
  const gst = Math.round(fee * 0.18);
  return { months, rate, emi: m, total_interest: interest, processing_fee: fee, gst_on_fee: gst, total_cost: interest + fee + gst };
}

export const cardEmiTable = (amount: number) => products.emi.tenures.map((t) => cardEmi(amount, t.months));

// ─── Credit card value from a spend profile ─────────────────────────────────

export type SpendProfile = Record<"dining" | "online" | "groceries" | "travel" | "fuel" | "utilities" | "other", number>;
export const EMPTY_PROFILE: SpendProfile = { dining: 0, online: 0, groceries: 0, travel: 0, fuel: 0, utilities: 0, other: 0 };

export interface CardValue {
  card_id: string;
  monthly_rewards: number;
  yearly_rewards: number;
  fuel_saving_yearly: number;
  lounge_value: number;
  fee: number;
  fee_waived: boolean;
  net_yearly: number;
  /** A known monthly income is below the card's `min_income_monthly`. */
  below_income: boolean;
}

/** CONTRACT.md "Card value": the yearly value of a card for a monthly spend profile. */
export function cardValue(card: CreditCardProduct, s: SpendProfile): CardValue {
  const model = products.card_value_model;
  const points = card.reward_type === "points";
  const rates = (points ? card.earn : card.cashback_rates) ?? {};
  const base = rates.base ?? 0;
  const per = card.earn_per ?? 100;
  const unit = (spend: number, r: number) => (points ? (spend * r) / per * card.point_value : (spend * r) / 100);
  const rateOf = (c: string) => (c in rates ? rates[c] : base);
  let fixed = 0;
  let extra = 0;
  for (const c of model.categories) {
    const spend = s[c as keyof SpendProfile] ?? 0;
    const r = rateOf(c);
    if (model.accelerated.includes(c)) {
      fixed += unit(spend, Math.min(r, base));
      extra += unit(spend, Math.max(0, r - base));
    } else {
      let term = unit(spend, r);
      if (c === "fuel" && card.caps.fuel_cashback_monthly != null) term = Math.min(term, card.caps.fuel_cashback_monthly);
      fixed += term;
    }
  }
  const cap = points
    ? card.caps.accelerated_points_monthly != null
      ? card.caps.accelerated_points_monthly * card.point_value
      : Infinity
    : card.caps.accelerated_cashback_monthly ?? Infinity;
  const monthly = fixed + Math.min(extra, cap);
  const fuelSaving = Math.min(s.fuel * 0.01, card.fuel.surcharge_waiver_cap_monthly) * 12;
  const lv = model.lounge_value;
  let lounge = 0;
  if (s.travel >= lv.travel_spend_threshold) {
    const dom = card.lounge.domestic_per_year == null ? lv.domestic_used_max : Math.min(card.lounge.domestic_per_year, lv.domestic_used_max);
    const intl = Math.min(card.lounge.international_per_year, lv.international_used_max);
    lounge = dom * lv.domestic + intl * lv.international;
  }
  const yearlySpend = 12 * Object.values(s).reduce((a, b) => a + b, 0);
  const waived = yearlySpend >= card.fee_waiver_spend;
  const fee = waived ? 0 : card.annual_fee;
  const yearly = monthly * 12;
  return {
    card_id: card.id,
    monthly_rewards: Math.round(monthly),
    yearly_rewards: Math.round(yearly),
    fuel_saving_yearly: Math.round(fuelSaving),
    lounge_value: lounge,
    fee: card.annual_fee,
    fee_waived: waived,
    net_yearly: Math.round(yearly + fuelSaving + lounge - fee),
    below_income: false,
  };
}

/** Every card ranked by its yearly value for `s`, best first. With a known monthly
 *  income, the cards it qualifies for come first and the rest follow, marked
 *  `below_income` (the brain's `rank_cards`, same rule). */
export function rankCards(s: SpendProfile, monthlyIncome?: number): CardValue[] {
  return products.credit_cards
    .map((c) => ({ ...cardValue(c, s), below_income: monthlyIncome != null && monthlyIncome < c.min_income_monthly }))
    .sort((a, b) => Number(a.below_income) - Number(b.below_income) || b.net_yearly - a.net_yearly || a.card_id.localeCompare(b.card_id));
}

/** The signed-in customer's own monthly spend profile: debits of the last 90 days in
 *  card-relevant categories, from savings and the credit card, divided by 3, rounded
 *  to the nearest ₹100. */
export function customerProfile(): SpendProfile {
  const p: SpendProfile = { ...EMPTY_PROFILE };
  const map = new Map(products.spend_categories.map((c) => [c.id, c.card_category]));
  for (const t of customer.transactions) {
    if (t.direction !== "debit" || t.days_ago >= 90 || t.account === "ca") continue;
    const k = map.get(t.category);
    if (!k) continue;
    p[k as keyof SpendProfile] += t.amount;
  }
  for (const k of Object.keys(p) as (keyof SpendProfile)[]) p[k] = Math.round(p[k] / 3 / 100) * 100;
  return p;
}

// ─── Loans ──────────────────────────────────────────────────────────────────

export interface Eligibility {
  loan_type: LoanProduct["id"];
  rate: number;
  tenure_months: number;
  max_emi: number | null;
  max_amount: number;
  /** The working, line by line, as the page shows it. */
  steps: string[];
}

/** CONTRACT.md "Loan eligibility". */
export function loanEligibility(
  loan: LoanProduct,
  input: { monthly_income?: number | null; existing_emis?: number | null; tenure_months?: number | null; gold_grams?: number | null },
): Eligibility {
  const rate = loan.rate_typical;
  const n = input.tenure_months ?? loan.tenure_default_months;
  if (loan.id === "gold") {
    const grams = input.gold_grams ?? 0;
    const per = loan.gold_rate_per_gram_22k ?? 0;
    const ltv = loan.ltv_pct ?? 75;
    const max = Math.min(loan.amount_max, Math.floor((grams * per * ltv) / 100 / 1000) * 1000);
    return {
      loan_type: loan.id,
      rate,
      tenure_months: n,
      max_emi: null,
      max_amount: max,
      steps: [`Gold value = ${grams} g × ₹${per.toLocaleString("en-IN")} = ₹${(grams * per).toLocaleString("en-IN")}`, `Loan up to ${ltv}% = ₹${max.toLocaleString("en-IN")}`],
    };
  }
  const income = input.monthly_income ?? 0;
  const existing = input.existing_emis ?? 0;
  const foir = loan.foir ?? 0.5;
  const maxEmi = Math.max(0, income * foir - existing);
  const r = rate / 12 / 100;
  const f = Math.pow(1 + r, n);
  const raw = (maxEmi * (f - 1)) / (r * f);
  const max = Math.min(loan.amount_max, Math.floor(raw / 10000) * 10000);
  return {
    loan_type: loan.id,
    rate,
    tenure_months: n,
    max_emi: Math.round(maxEmi),
    max_amount: Math.max(0, max),
    steps: [
      `EMI you can afford = ₹${income.toLocaleString("en-IN")} × ${Math.round(foir * 100)}% − ₹${existing.toLocaleString("en-IN")} existing EMIs = ₹${Math.round(maxEmi).toLocaleString("en-IN")}`,
      `At ${rate}% for ${n} months, that EMI repays ₹${Math.max(0, max).toLocaleString("en-IN")}`,
    ],
  };
}

// ─── Fixed deposits ─────────────────────────────────────────────────────────

export function fdRate(months: number): number | null {
  return products.fd.rates.find((r) => months >= r.min_months && months <= r.max_months)?.rate ?? null;
}

/** Cumulative maturity (quarterly compounding), or the periodic payout. */
export function fdQuote(amount: number, months: number, payout: "cumulative" | "monthly" | "quarterly") {
  const rate = fdRate(months) ?? 0;
  if (payout === "cumulative") {
    const maturity = Math.round(amount * Math.pow(1 + rate / 400, (4 * months) / 12));
    return { rate, maturity, interest: maturity - amount, payout_each: 0 };
  }
  const each = Math.round((amount * rate) / 100 / (payout === "monthly" ? 12 : 4));
  return { rate, maturity: amount, interest: Math.round((amount * rate * months) / 1200), payout_each: each };
}
