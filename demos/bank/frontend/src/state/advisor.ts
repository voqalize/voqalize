/**
 * The advisor pages' state: the card spend profile and compare order, the
 * card EMI planner, and each loan's calculator and eligibility inputs. One
 * store for a visitor's taps and the agent's moves alike; the brain hears
 * `cards_profile_changed` and `loan_calc_changed` (debounced) from here.
 */
import { create } from "zustand";
import { customer, loanProduct, products } from "../data/bank";
import { EMPTY_PROFILE, emi, rankCards, type SpendProfile } from "../lib/bankmath";
import { type By, currentBy, emit } from "../voice/events";
import { useSession } from "./session";

export type LoanType = "home" | "personal" | "gold" | "car";
export const LOAN_TYPES: LoanType[] = ["home", "personal", "gold", "car"];
export const SPEND_KEYS = Object.keys(EMPTY_PROFILE) as (keyof SpendProfile)[];

/** A typical city household's month, so the ranking means something before anyone types. */
export const SAMPLE_PROFILE: SpendProfile = { dining: 6000, online: 8000, groceries: 9000, travel: 3000, fuel: 4000, utilities: 5000, other: 6000 };

export interface LoanCalc {
  amount: number;
  tenure: number;
  rate: number;
}
export interface EligInput {
  monthly_income: number;
  existing_emis: number;
  tenure_months: number;
  gold_grams: number;
}

function defaultCalc(t: LoanType): LoanCalc {
  const l = loanProduct(t)!;
  const amount = { home: 5000000, personal: 500000, gold: 200000, car: 800000 }[t];
  return { amount: Math.min(l.amount_max, Math.max(l.amount_min, amount)), tenure: l.tenure_default_months, rate: l.rate_typical };
}
function defaultElig(t: LoanType): EligInput {
  const l = loanProduct(t)!;
  return { monthly_income: 75000, existing_emis: 0, tenure_months: l.tenure_default_months, gold_grams: 40 };
}

interface Advisor {
  profile: SpendProfile;
  /** True once "Use my real spend" (or the agent) filled it from the customer's data. */
  fromCustomer: boolean;
  compare: string[] | null;
  emiTxn: string | null;
  emiAmount: number;
  emiTenure: number;
  calc: Record<LoanType, LoanCalc>;
  elig: Record<LoanType, EligInput>;
  /** Loans whose eligibility has been checked (the result shows). */
  checked: Record<LoanType, boolean>;
  setProfile: (p: Partial<SpendProfile>, fromCustomer?: boolean) => void;
  setCompare: (ids: string[] | null) => void;
  setEmi: (p: { txn?: string | null; amount?: number; tenure?: number }) => void;
  setCalc: (t: LoanType, p: Partial<LoanCalc>) => void;
  setElig: (t: LoanType, p: Partial<EligInput>, checked?: boolean) => void;
}

const by4 = <T>(f: (t: LoanType) => T) => Object.fromEntries(LOAN_TYPES.map((t) => [t, f(t)])) as Record<LoanType, T>;

export const useAdvisor = create<Advisor>((set, get) => ({
  profile: { ...SAMPLE_PROFILE },
  fromCustomer: false,
  compare: null,
  emiTxn: null,
  emiAmount: 50000,
  emiTenure: 6,
  calc: by4(defaultCalc),
  elig: by4(defaultElig),
  checked: by4(() => false),
  setProfile: (p, fromCustomer = false) => {
    set({ profile: { ...get().profile, ...p }, fromCustomer });
    profileChanged();
  },
  setCompare: (ids) => set({ compare: ids }),
  setEmi: (p) =>
    set((s) => ({
      emiTxn: p.txn !== undefined ? p.txn : s.emiTxn,
      emiAmount: p.amount ?? s.emiAmount,
      emiTenure: p.tenure ?? s.emiTenure,
    })),
  setCalc: (t, p) => {
    set((s) => ({ calc: { ...s.calc, [t]: { ...s.calc[t], ...p } } }));
    calcChanged(t);
  },
  setElig: (t, p, checked = true) => set((s) => ({ elig: { ...s.elig, [t]: { ...s.elig[t], ...p } }, checked: { ...s.checked, [t]: checked || s.checked[t] } })),
}));

/** The signed-in customer's monthly income, which the card ranking checks against each
 *  card's minimum; unknown (undefined) for a signed-out visitor. */
export const knownIncome = (): number | undefined => (useSession.getState().signedIn ? customer.profile.monthly_income : undefined);

/** The cards ranked for the current profile and, signed in, her income. */
export const rankForVisitor = (p: SpendProfile) => rankCards(p, knownIncome());

/** The cards in compare order: the chosen ones, else the top three for the profile. */
export function compareIds(): string[] {
  const s = useAdvisor.getState();
  return s.compare && s.compare.length >= 2 ? s.compare : rankForVisitor(s.profile).slice(0, 3).map((v) => v.card_id);
}

/** Prefill eligibility with the signed-in customer's own income and EMIs. */
export function customerElig(): Pick<EligInput, "monthly_income" | "existing_emis"> {
  return { monthly_income: customer.profile.monthly_income, existing_emis: customer.loans.reduce((a, l) => a + l.emi, 0) };
}

export const loanEmi = (c: LoanCalc) => Math.round(emi(c.amount, c.rate, c.tenure));

// ─── Events, debounced ──────────────────────────────────────────────────────

let profileTimer: ReturnType<typeof setTimeout> | undefined;
let profileBy: By | null = null;
function profileChanged() {
  const by = currentBy();
  profileBy = profileBy === "agent" ? "agent" : by;
  clearTimeout(profileTimer);
  profileTimer = setTimeout(() => {
    const p = useAdvisor.getState().profile;
    emit("cards_profile_changed", { ...p, top: rankForVisitor(p).map((v) => v.card_id) }, profileBy ?? by);
    profileBy = null;
  }, 600);
}

const calcTimers: Partial<Record<LoanType, ReturnType<typeof setTimeout>>> = {};
const calcBy: Partial<Record<LoanType, By>> = {};
function calcChanged(t: LoanType) {
  const by = currentBy();
  calcBy[t] = calcBy[t] === "agent" ? "agent" : by;
  clearTimeout(calcTimers[t]);
  calcTimers[t] = setTimeout(() => {
    const c = useAdvisor.getState().calc[t];
    emit("loan_calc_changed", { loan_type: t, amount: c.amount, tenure_months: c.tenure, rate: c.rate, emi: loanEmi(c) }, calcBy[t] ?? by);
    delete calcBy[t];
  }, 600);
}

export const tenures = () => products.emi.tenures.map((t) => t.months);
