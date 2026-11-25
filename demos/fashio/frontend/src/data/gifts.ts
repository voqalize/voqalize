/**
 * The gift finder's pick (CONTRACT.md, "Gifts"), the same as the brain's
 * `pick_gifts` in backend/fashio.py. The page runs it for "Show ideas" by
 * hand; on a call the brain picks, writes a reason for each and sends
 * `gifts.show`.
 */
import { type Product, index } from "./catalog";
import { STORE } from "./shop";

export interface GiftBrief {
  recipient?: string;
  occasion?: string;
  /** Rupees; 0 or absent: no limit. */
  budget_max?: number;
  size?: string;
  colours?: string[];
  patterns?: string[];
  material?: string;
}

const SIDE_GENDERS: Record<string, string[]> = {
  women: ["women", "unisex"],
  men: ["men", "unisex"],
  kids: ["boys", "girls"],
};

export function sideOf(recipient?: string): string | null {
  if (!recipient) return null;
  const key = Object.keys(STORE.gifts.recipient_gender).find((k) => k.toLowerCase() === recipient.toLowerCase());
  return key ? STORE.gifts.recipient_gender[key] : null;
}

function words(p: Product): string {
  return `${p.name} ${Object.values(p.attrs ?? {}).join(" ")}`.toLowerCase();
}

export function giftScore(p: Product, b: GiftBrief): number {
  let s = 0;
  if (b.colours?.some((c) => c.toLowerCase() === p.colour.toLowerCase())) s += 3;
  const w = words(p);
  if ([...(b.patterns ?? []), ...(b.material ? [b.material] : [])].some((x) => x && w.includes(x.toLowerCase()))) s += 2;
  if (b.occasion && STORE.gifts.festive_occasions.includes(b.occasion) && p.usage === "Ethnic") s += 2;
  return s;
}

export function pickGifts(b: GiftBrief, n = 6, products: Product[] = index()?.products ?? []): Product[] {
  const side = sideOf(b.recipient);
  const types = STORE.gifts.ideas[side ?? "any"] ?? [];
  const genders = side ? SIDE_GENDERS[side] : null;
  const pool = products.filter((p) => {
    if (!types.includes(p.type)) return false;
    if (genders && !genders.includes(p.gender)) return false;
    if (b.budget_max && p.price > b.budget_max) return false;
    if (p.scale === "one") return p.sizes.some(([, k]) => k > 0);
    return !!b.size && p.sizes.some(([l, k]) => k > 0 && l.toUpperCase() === b.size!.toUpperCase());
  });
  pool.sort((x, y) => giftScore(y, b) - giftScore(x, b) || x.rank - y.rank);
  const out: Product[] = [];
  const seen = new Set<string>();
  for (const p of pool) {
    if (seen.has(p.type)) continue;
    seen.add(p.type);
    out.push(p);
    if (out.length >= n) break;
  }
  return out;
}

/** The gift finder's pattern and material chips (the scene's `gifts.brief` words). */
export const PATTERNS = ["Solid", "Printed", "Striped", "Checked", "Embroidered"];
export const MATERIALS = ["Cotton", "Silk", "Leather", "Steel", "Denim", "Wool"];

/**
 * A short, plain reason for a pick shown by hand (on a call the brain writes
 * its own): the type, then the brief's strongest match from the data.
 */
export function giftReason(p: Product, b: GiftBrief, label: (type: string) => string = (t) => t): string {
  const what = label(p.type);
  if (b.colours?.some((c) => c.toLowerCase() === p.colour.toLowerCase())) return `${what} in their colour (${p.colour.toLowerCase()})`;
  const w = `${p.name} ${Object.values(p.attrs ?? {}).join(" ")}`.toLowerCase();
  const hit = [...(b.patterns ?? []), ...(b.material ? [b.material] : [])].find((x) => x && w.includes(x.toLowerCase()));
  if (hit) return `${what}, ${hit.toLowerCase()} as you asked`;
  if (b.occasion && STORE.gifts.festive_occasions.includes(b.occasion) && p.usage === "Ethnic") return `${what}, festive enough for ${b.occasion}`;
  if (b.budget_max) return `${what} under your ₹${b.budget_max.toLocaleString("en-IN")} budget`;
  return p.scale === "one" ? `${what}: one size, no guessing` : `${what}, in stock in size ${b.size}`;
}
