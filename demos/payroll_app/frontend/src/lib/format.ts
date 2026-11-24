/** Indian English formatting: ₹ with Indian grouping, dates as 16 Feb 2026. */

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** 125000 → "1,25,000". */
export const num = (n: number): string => inr.format(Math.round(n));
/** 125000 → "₹1,25,000"; negatives as "−₹1,25,000". */
export const rupees = (n: number): string => (n < 0 ? `−₹${num(-n)}` : `₹${num(n)}`);
/** A change: "+₹1,200", "−₹1,200", "₹0". */
export const delta = (n: number): string => (n > 0 ? `+₹${num(n)}` : n < 0 ? `−₹${num(-n)}` : "₹0");

/** "2026-02-16" → "16 Feb 2026". */
export function date(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m) return iso;
  return d ? `${d} ${MONTHS[m - 1]} ${y}` : `${MONTHS[m - 1]} ${y}`;
}
/** "2026-02-16" → "16 Feb". */
export function shortDate(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]}`;
}
/** "2026-01" → "January 2026". */
export function monthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS_LONG[m - 1]} ${y}`;
}
/** "2026-01" → "Jan 2026". */
export function monthShort(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}
/** Days as said: 1 → "1 day", 2.5 → "2.5 days". */
export const days = (n: number): string => `${n} day${n === 1 ? "" : "s"}`;
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");

/** Rupees as a person might say them: "720000", "7,20,000", "₹7.2 lakh", "7.2L". */
export function parseRupees(raw: string | number): number | null {
  if (typeof raw === "number") return Number.isFinite(raw) ? Math.round(raw) : null;
  const s = raw.toLowerCase().replace(/[₹,\s]|rs\.?|inr/g, "");
  const m = /^(\d+(?:\.\d+)?)(lakhs?|lacs?|l|crores?|cr|k)?$/.exec(s);
  if (!m) return null;
  const n = Number(m[1]);
  const unit = m[2] ?? "";
  const mult = unit.startsWith("l") ? 100000 : unit.startsWith("c") ? 10000000 : unit === "k" ? 1000 : 1;
  return Math.round(n * mult);
}
