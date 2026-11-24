/**
 * "Spending" (insights screen, dashboard month figures, `insights.show`):
 * debits from the personal accounts — savings `sb` and the credit card `cc`,
 * never the business current account `ca` — in a calendar month, every category
 * except transfers (card bill payments are transfers, so nothing counts twice),
 * investments, income and refunds. The brain uses the same rule.
 */
import { type Txn, categoryName, daysAgo, monthKey } from "../data/bank";
import { allTxns } from "../state/bank";

export const SPEND_EXCLUDED = ["transfers", "investments", "income", "refunds"];
export const isSpend = (t: Txn) => t.direction === "debit" && t.account !== "ca" && !SPEND_EXCLUDED.includes(t.category);
export const txnMonth = (t: Txn) => monthKey(daysAgo(t.days_ago));

/** The spending transactions of a month (YYYY-MM). */
export const spendingTxns = (month: string, all: Txn[] = allTxns()) => all.filter((t) => isSpend(t) && txnMonth(t) === month);

export interface MonthSpend {
  month: string;
  total: number;
  categories: { id: string; name: string; amount: number; count: number }[];
}

const r2 = (n: number) => Math.round(n * 100) / 100;

export function spendByCategory(month: string, all: Txn[] = allTxns()): MonthSpend {
  const by = new Map<string, { amount: number; count: number }>();
  let total = 0;
  for (const t of spendingTxns(month, all)) {
    const e = by.get(t.category) ?? { amount: 0, count: 0 };
    e.amount += t.amount;
    e.count += 1;
    by.set(t.category, e);
    total += t.amount;
  }
  const categories = [...by.entries()]
    .map(([id, e]) => ({ id, name: categoryName(id), amount: r2(e.amount), count: e.count }))
    .sort((a, b) => b.amount - a.amount);
  return { month, total: r2(total), categories };
}

/** Months (YYYY-MM, newest first) with any transaction. */
export const txnMonths = (all: Txn[] = allTxns()) => [...new Set(all.map(txnMonth))].sort().reverse();

/** The month before `month`. */
export function prevMonth(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return monthKey(new Date(y, m - 2, 1));
}
