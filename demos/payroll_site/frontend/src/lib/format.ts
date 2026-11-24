/** Indian formats: ₹1,25,000; DD MMM YYYY; times in IST. */

export function grouped(n: number): string {
  const sign = n < 0 ? "-" : "";
  const s = String(Math.abs(Math.round(n)));
  if (s.length <= 3) return sign + s;
  let head = s.slice(0, -3);
  const tail = s.slice(-3);
  const groups: string[] = [];
  while (head.length > 2) {
    groups.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  if (head) groups.unshift(head);
  return `${sign}${groups.join(",")},${tail}`;
}

export const inr = (n: number) => (n < 0 ? `−₹${grouped(-n)}` : `₹${grouped(n)}`);

/** ₹16.8 lakh, ₹1.2 crore: the way a sales page says a big number. */
export function lakh(n: number): string {
  if (n >= 1e7) return `₹${+(n / 1e7).toFixed(2)} crore`;
  if (n >= 1e5) return `₹${+(n / 1e5).toFixed(1)} lakh`;
  return inr(n);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** "2026-11-19" → "19 Nov 2026". */
export function dmy(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${String(d).padStart(2, "0")} ${MONTHS[m - 1]} ${y}`;
}

/** "2026-11-19" → "Thu". */
export function weekday(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return DAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
}

/** "15:30" → "3:30 pm". */
export function time12(t: string): string {
  const [h, m] = t.split(":").map(Number);
  const suffix = h < 12 ? "am" : "pm";
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${suffix}`;
}
