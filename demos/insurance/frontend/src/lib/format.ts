/** Indian digit grouping: 125000 → "1,25,000". */
export function groupIndian(n: number): string {
  const s = String(Math.floor(Math.abs(n)));
  if (s.length <= 3) return s;
  let head = s.slice(0, -3);
  const tail = s.slice(-3);
  const groups: string[] = [];
  while (head.length > 2) {
    groups.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  if (head) groups.unshift(head);
  return `${groups.join(",")},${tail}`;
}

/** ₹1,25,000 (and −₹2,500 for a discount). */
export function inr(amount: number): string {
  const n = Math.floor(Math.abs(amount) + 0.5 + 1e-9);
  return `${amount < 0 ? "−" : ""}₹${groupIndian(n)}`;
}

/** A plain-ASCII version for lines the agent reads ("-₹2,500"). */
export function inrPlain(amount: number): string {
  return inr(amount).replace("−", "-");
}

/** "14.5 lakh", "1.2 crore": the way an amount is said. */
export function inWords(n: number): string {
  if (n >= 1e7) return `${trim(n / 1e7)} crore`;
  if (n >= 1e5) return `${trim(n / 1e5)} lakh`;
  if (n >= 1e3) return `${trim(n / 1e3)} thousand`;
  return String(n);
}
const trim = (x: number) => String(Math.round(x * 100) / 100);

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-04-12" → "12 Apr 2026". */
export function fmtDate(iso: string | undefined | null): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${m[3]} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

/** Whole days from today (local) to an ISO date. */
export function daysUntil(iso: string, today = new Date()): number {
  const [y, mo, d] = iso.split("-").map(Number);
  const t = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((Date.UTC(y, mo - 1, d) - t) / 86400000);
}

export function fileSize(bytes: number): string {
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
