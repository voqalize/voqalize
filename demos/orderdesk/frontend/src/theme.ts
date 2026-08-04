/**
 * OrderDesk's visual identity, in one place.
 *
 * MedSetu is a distributor's trade app, not a consumer wellness app: dense rows,
 * hard edges, numbers everywhere. The palette is deep navy + slate (the console)
 * with a saffron accent (the brand, and every "act now" affordance), and three
 * status colours that carry the whole line-item state machine:
 *
 *     grey  → resolving (the catalog is still thinking)
 *     amber → ambiguous (multi_variant / multi_family — a tap or a word is needed)
 *     green → matched   (locked to a SKU, priced, orderable)
 *
 * Both the call bar (`OrderDeskCall.tsx`) and the screens (`pages.tsx`) read from
 * here, so the two never drift.
 */

// ── Ink & surfaces ───────────────────────────────────────────────────────────
export const INK = "#0D1726";
export const INK_SOFT = "#5A6B82";
export const INK_FAINT = "#8A99AE";
export const BG = "#EDF1F7";
export const CARD = "#FFFFFF";
export const LINE = "#DCE3EC";
export const LINE_SOFT = "#EAEFF5";

// ── Brand ────────────────────────────────────────────────────────────────────
export const NAVY = "#16305C";
export const NAVY_DEEP = "#0B1B33";
export const NAVY_TINT = "#EAF0FA";
export const SAFFRON = "#E07B0E";
export const SAFFRON_DEEP = "#B45F06";
export const SAFFRON_TINT = "#FDF2E1";

// ── Status ───────────────────────────────────────────────────────────────────
export const GREY = "#93A2B6";
export const GREY_TINT = "#F1F4F9";
export const AMBER = "#C2790F";
export const AMBER_TINT = "#FCF3E3";
export const AMBER_LINE = "#EFD9AE";
export const GREEN = "#12805A";
export const GREEN_TINT = "#E7F4EF";
export const GREEN_LINE = "#BFE2D5";
export const RED = "#C0392B";

/** The lock screen / call chrome / order-placed backdrop. */
export const CALL_BG = "linear-gradient(160deg, #0B1B33 0%, #14294B 55%, #1B3A66 100%)";

export const FONT_IMPORT = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Noto+Sans+Devanagari:wght@400;500;600;700&display=swap');
`;

/** Inter for the console; Noto Sans Devanagari so presenter hints render properly. */
export const BODY = "'Inter', 'Noto Sans Devanagari', system-ui, -apple-system, sans-serif";
/** SKU codes, pack sizes, money — tabular, so columns line up down a dense list. */
export const MONO = "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, monospace";

/** ₹ with no decimals — trade prices are read at a glance. */
export function rupees(n: number): string {
  return `₹${Math.round(n).toLocaleString("en-IN")}`;
}

/** ₹ keeping paise — PTRs are quoted to two places on a single SKU. */
export function rupeesExact(n: number): string {
  return `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
