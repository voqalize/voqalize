/**
 * The signed-in customer's mutable state, seeded from customer.json: balances,
 * card controls and limits, what the confirmation sheet has done (bill payments,
 * transfers, FDs, EMI conversions, accepted offers, each with the transactions it
 * made) and the screens' own state the performers drive (the transactions filter
 * and open transaction, the insights month). Kept in sessionStorage so a refresh
 * keeps the demo where it was.
 *
 * Writes go through `applyAction` (src/app/actions.ts) after a confirmation; the
 * screens' own state is set directly. Performers wrap their writes in `asAgent`.
 */
import { create } from "zustand";
import {
  type AccountId,
  type BankCard,
  type CardControls,
  type Customer,
  type Txn,
  type TxnFilter,
  customer,
  monthKey,
  today,
} from "../data/bank";
import { emit } from "../voice/events";

export type CardId = "debit" | "credit";
export type Deposit = Customer["deposits"][number] & { reference?: string };

export interface CardState {
  controls: CardControls;
  limits: Record<string, number>;
}

export interface EmiConversion {
  txn_id: string;
  tenure_months: number;
  rate: number;
  emi: number;
  total_cost: number;
  reference: string;
}

export interface BankState {
  balances: Record<AccountId, number>;
  cards: Record<CardId, CardState>;
  /** Credit card money that moves: outstanding, available. */
  cc: { outstanding: number; available: number };
  /** Transactions made by actions here, newest first (ids N0001…). */
  extraTxns: Txn[];
  seq: number;
  billsPaid: Record<string, { amount: number; reference: string }>;
  deposits: Deposit[];
  emi: Record<string, EmiConversion>;
  offers: Record<string, { reference: string; amount?: number; tenure_months?: number; emi?: number }>;
  transfers: { reference: string; beneficiary: string; amount: number; from: AccountId }[];

  filter: TxnFilter;
  selectedTxn: string | null;
  insightsMonth: string;

  setFilter: (patch: Partial<TxnFilter>) => void;
  clearFilter: () => void;
  openTxn: (id: string | null) => void;
  setInsightsMonth: (m: string) => void;
  reset: () => void;
}

const KEY = "globalbank-state";

function seed() {
  const card = (c: BankCard): CardState => ({ controls: { ...c.controls }, limits: { ...c.limits } });
  const debit = customer.cards.find((c) => c.id === "debit")!;
  const credit = customer.cards.find((c) => c.id === "credit")!;
  return {
    balances: Object.fromEntries(customer.accounts.map((a) => [a.id, a.balance])) as Record<AccountId, number>,
    cards: { debit: card(debit), credit: card(credit) },
    cc: { outstanding: credit.outstanding ?? 0, available: credit.available ?? 0 },
    extraTxns: [] as Txn[],
    seq: 0,
    billsPaid: {},
    deposits: customer.deposits.map((d) => ({ ...d })),
    emi: {},
    offers: {},
    transfers: [],
    filter: {} as TxnFilter,
    selectedTxn: null as string | null,
    insightsMonth: monthKey(today()),
  };
}

type Data = ReturnType<typeof seed>;

function load(): Partial<Data> {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return {};
    const saved = JSON.parse(raw) as Partial<Data> & { day?: string };
    // Data is relative to today: a state saved on another day starts over.
    if (saved.day !== monthKey(today()) + "-" + today().getDate()) return {};
    return saved;
  } catch {
    return {};
  }
}

export const useBank = create<BankState>((set) => ({
  ...seed(),
  ...load(),
  setFilter: (patch) => set((s) => ({ filter: { ...s.filter, ...patch } })),
  clearFilter: () => set({ filter: {} }),
  openTxn: (id) => {
    set({ selectedTxn: id });
    if (id) emit("txn_opened", { txn_id: id });
  },
  setInsightsMonth: (m) => set({ insightsMonth: m }),
  reset: () => set(seed()),
}));

useBank.subscribe((s) => {
  try {
    const { setFilter: _a, clearFilter: _b, openTxn: _c, setInsightsMonth: _d, reset: _e, ...data } = s;
    sessionStorage.setItem(KEY, JSON.stringify({ ...data, day: monthKey(today()) + "-" + today().getDate() }));
  } catch {
    /* private mode */
  }
});

// ─── Derived ────────────────────────────────────────────────────────────────

let memo: { extra: Txn[]; all: Txn[] } | null = null;
/** Every transaction: the ones actions made here first, then customer.json's. */
export function allTxns(s: Pick<BankState, "extraTxns"> = useBank.getState()): Txn[] {
  if (memo?.extra === s.extraTxns) return memo.all;
  const all = [...s.extraTxns, ...customer.transactions];
  memo = { extra: s.extraTxns, all };
  return all;
}

/** React: every transaction (stable between unrelated store changes). */
export const useAllTxns = () => useBank((s) => allTxns(s));

export const findTxn = (id: string) => allTxns().find((t) => t.id === id);

/** A filter is "empty" when it would show everything. */
export const filterIsEmpty = (f: TxnFilter) =>
  !f.category && !f.query && f.from_days_ago == null && f.to_days_ago == null && f.min_amount == null && f.max_amount == null && (!f.account || f.account === "all") && (!f.direction || f.direction === "any");

// ─── Writes used by actions.ts ─────────────────────────────────────────────

export function addTxn(t: Omit<Txn, "id" | "days_ago" | "ref" | "emi_eligible"> & Partial<Pick<Txn, "ref">>): Txn {
  const s = useBank.getState();
  const seq = s.seq + 1;
  const txn: Txn = {
    id: `N${String(seq).padStart(4, "0")}`,
    days_ago: 0,
    ref: t.ref ?? String(Math.floor(100000000000 + Math.random() * 899999999999)),
    emi_eligible: false,
    ...t,
  };
  useBank.setState({ seq, extraTxns: [txn, ...s.extraTxns] });
  return txn;
}

/** Move money out of (negative) or into an account; returns the new balance. */
export function moveBalance(acc: AccountId, delta: number): number {
  const s = useBank.getState();
  const next = Math.round((s.balances[acc] + delta) * 100) / 100;
  useBank.setState({ balances: { ...s.balances, [acc]: next } });
  return next;
}
