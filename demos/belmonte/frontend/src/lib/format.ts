/** US formats for the guest app: $1,234.50, 2:40 PM, Wed, Nov 25. */

/** Round half up to the cent, as the brain does (`hotel.cents`). */
export const cents = (x: number) => Math.floor(x * 100 + 0.5 + 1e-9) / 100;

export function money(x: number): string {
  const v = cents(Math.abs(x)).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${x < 0 ? "-" : ""}$${v}`;
}

/** A price without cents when it is whole: $16, $18.50. */
export function price(x: number): string {
  return Number.isInteger(x) ? `$${x.toLocaleString("en-US")}` : money(x);
}

export const minutes = (t: string) => {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
};
export const hhmm = (n: number) => `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;

/** 14:40 → 2:40 PM; 24:00 → midnight. */
export function clock(t: string): string {
  const n = minutes(t);
  if (n && n % 1440 === 0) return "midnight";
  const h = Math.floor((n % 1440) / 60);
  const m = n % 60;
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const parse = (d: string) => {
  const [y, m, dd] = d.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, dd));
};

/** 2026-11-25 → Wed, Nov 25. */
export function day(d: string): string {
  const x = parse(d);
  return `${DAYS[x.getUTCDay()]}, ${MONTHS[x.getUTCMonth()]} ${x.getUTCDate()}`;
}
/** 2026-11-25 → Nov 25. */
export function shortDay(d: string): string {
  const x = parse(d);
  return `${MONTHS[x.getUTCMonth()]} ${x.getUTCDate()}`;
}

export function datesBetween(a: string, b: string): string[] {
  const out: string[] = [];
  for (let t = parse(a).getTime(); t <= parse(b).getTime(); t += 86400000) out.push(new Date(t).toISOString().slice(0, 10));
  return out;
}

export const nightsBetween = (a: string, b: string) => Math.round((parse(b).getTime() - parse(a).getTime()) / 86400000);
