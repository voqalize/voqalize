/**
 * Find my size: the size advisor's rule (CONTRACT.md, "Fit"), the same as the
 * brain's `recommend` in backend/fashio.py. The page runs it when the shopper
 * fills the panel by hand; on a call the brain runs it and sends `fit.recommend`.
 */
import type { Product } from "./catalog";
import { STORE } from "./shop";

export type FitPref = "snug" | "regular" | "relaxed";

export interface FitInput {
  usual_size?: string;
  fit?: FitPref;
  height_cm?: number;
}

export interface FitAnswer {
  /** The size to buy: in stock. */
  size: string;
  /** The size the rule chose, when it is out of stock and `size` replaces it. */
  wanted?: string;
  /** The steps from the shopper's usual size and why. */
  steps: number;
  why: "same" | "slim_up" | "loose_down" | "tall_up";
  cut: "slim" | "loose" | "regular";
}

const ALPHA = ["XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"];
const WAIST: Record<string, Record<string, number>> = {
  women: { XS: 26, S: 28, M: 30, L: 32, XL: 34, XXL: 36, "3XL": 38 },
  men: { XS: 28, S: 30, M: 32, L: 34, XL: 36, XXL: 38, "3XL": 40 },
};

function order(scale: string, label: string): number {
  if (scale === "alpha") return ALPHA.indexOf(label);
  if (scale === "waist") return Number(label);
  if (scale === "uk") return Number(label.replace(/\D+/g, ""));
  if (scale === "age") {
    const m = /^(\d+)(?:-(\d+))?([YM])$/.exec(label);
    if (!m) return 99;
    const n = Number(m[2] ?? m[1]);
    return m[3] === "M" ? n / 12 : n;
  }
  return 0;
}

/** The shopper's usual size in the product's scale, or null when it does not convert. */
export function baseSize(p: Product, usual: string): string | null {
  const u = usual.trim().toUpperCase().replace(/^UK\s*/, "UK ").replace("XXXL", "3XL").replace("2XL", "XXL");
  const side = p.gender === "women" || p.gender === "girls" ? "women" : "men";
  if (p.scale === "uk") {
    const n = /(\d+)/.exec(u)?.[1];
    return n ? `UK ${n}` : null;
  }
  if (p.scale === "alpha") {
    if (ALPHA.includes(u)) return u;
    if (/^\d+$/.test(u)) {
      const hit = Object.entries(WAIST[side]).find(([, w]) => w === Number(u));
      return hit ? hit[0] : null;
    }
    return null;
  }
  if (p.scale === "waist") {
    if (/^\d+$/.test(u)) return u;
    const w = WAIST[side][u];
    return w ? String(w) : null;
  }
  if (p.scale === "age") return /^\d+(-\d+)?[YM]$/.test(u) ? u : null;
  return null;
}

export function cutOf(p: Product): "slim" | "loose" | "regular" {
  const fit = (p.attrs?.Fit ?? "").toLowerCase();
  if (STORE.fit.slim_words.some((w) => fit.includes(w))) return "slim";
  if (STORE.fit.loose_words.some((w) => fit.includes(w))) return "loose";
  return "regular";
}

export function recommend(p: Product, input: FitInput): FitAnswer | null {
  if (p.scale === "one" || !input.usual_size) return null;
  const base = baseSize(p, input.usual_size);
  if (!base) return null;
  const pref = input.fit ?? "regular";
  const cut = cutOf(p);
  let steps = 0;
  let why: FitAnswer["why"] = "same";
  if (pref === "relaxed" && cut === "slim") [steps, why] = [1, "slim_up"];
  else if (pref === "snug" && cut === "loose") [steps, why] = [-1, "loose_down"];
  else if ((input.height_cm ?? 0) >= STORE.fit.tall_cm && STORE.fit.length_types.includes(p.type) && (p.scale === "alpha" || p.scale === "waist")) [steps, why] = [1, "tall_up"];
  const labels = p.sizes.map(([l]) => l);
  // Where the base sits among the product's sizes (nearest when it does not stock it).
  const b = order(p.scale, base);
  let at = labels.indexOf(base);
  if (at < 0) {
    let best = Infinity;
    labels.forEach((l, i) => {
      const d = Math.abs(order(p.scale, l) - b);
      if (d < best || (d === best && order(p.scale, l) > order(p.scale, labels[at] ?? l))) [best, at] = [d, i];
    });
  }
  const wantedAt = Math.min(Math.max(at + steps, 0), labels.length - 1);
  const wanted = labels[wantedAt];
  if ((p.sizes[wantedAt]?.[1] ?? 0) > 0) return { size: wanted, steps, why, cut };
  // Out of stock: the nearest in-stock size; a tie goes to the larger.
  let pick = -1;
  for (let d = 1; d < labels.length && pick < 0; d++) {
    if ((p.sizes[wantedAt + d]?.[1] ?? 0) > 0) pick = wantedAt + d;
    else if ((p.sizes[wantedAt - d]?.[1] ?? 0) > 0) pick = wantedAt - d;
  }
  if (pick < 0) return null;
  return { size: labels[pick], wanted, steps, why, cut };
}
