/**
 * The quote builder's state, and the actions that change it. A click on the
 * form and a `quote.*` move call the same functions here; each change is sent
 * to the brain as `quote.changed`.
 */
import { create } from "zustand";
import { PRODUCT_IDS, cities, fieldOf, productById, quoteOptions } from "../data";
import type { ProductId, QuoteField } from "../data/types";
import { inr } from "../lib/format";
import { type Quote, defaultAddons, fieldDefaults, quote } from "../quote/rating";
import { emit } from "../stage/events";

interface QuoteState {
  /** The product whose builder is on screen (or was last). */
  product: ProductId;
  answers: Record<ProductId, Record<string, string>>;
  addons: Record<ProductId, string[]>;
  /** The field or add-on that changed last, for the slide-in and the event. */
  last: { product: ProductId; id: string; n: number } | null;
}

const init = <T>(fn: (p: ProductId) => T) => Object.fromEntries(PRODUCT_IDS.map((p) => [p, fn(p)])) as Record<ProductId, T>;

export const useQuote = create<QuoteState>(() => ({
  product: "car",
  answers: init((p) => fieldDefaults(p)),
  addons: init((p) => defaultAddons(p)),
  last: null,
}));

/** Only the answers that pass their field's checks reach the engine. */
export function validAnswers(product: ProductId, answers: Record<string, string>): Record<string, string> {
  const spec = productById(product)!;
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(answers)) {
    const f = fieldOf(spec, k);
    if (f && v !== "" && checkValue(f, v).ok) out[k] = v;
  }
  return out;
}

export function quoteFor(product: ProductId, s: QuoteState = useQuote.getState()): Quote {
  return quote(product, validAnswers(product, s.answers[product]), s.addons[product]);
}

export type Checked = { ok: true; value: string } | { ok: false; why: string; options?: string[] };

/** Is `raw` a value this field takes? Returns the value as the form stores it. */
export function checkValue(f: QuoteField, raw: string): Checked {
  const v = String(raw ?? "").trim();
  if (f.type === "select") {
    const opts = quoteOptions(f);
    const hit =
      opts.find((o) => o.value === v) ??
      opts.find((o) => o.value.toLowerCase() === v.toLowerCase() || o.label.toLowerCase() === v.toLowerCase());
    if (hit) return { ok: true, value: hit.value };
    return { ok: false, why: `${f.label} takes one of the listed options`, options: opts.map((o) => o.value) };
  }
  if (f.type === "integer" || f.type === "money") {
    const digits = v.replace(/[₹,\s]/g, "");
    if (!/^\d+$/.test(digits)) return { ok: false, why: `${f.label} needs a whole number` };
    const n = Number(digits);
    if (f.min !== undefined && n < f.min) return { ok: false, why: `${f.label} is at least ${f.type === "money" ? inr(f.min) : f.min}` };
    if (f.max !== undefined && n > f.max) return { ok: false, why: `${f.label} is at most ${f.type === "money" ? inr(f.max) : f.max}` };
    return { ok: true, value: String(n) };
  }
  return v ? { ok: true, value: v } : { ok: false, why: `${f.label} is empty` };
}

/** What a field's value looks like on screen: an option's label, ₹ for money. */
export function displayValue(f: QuoteField, v: string): string {
  if (f.type === "select") return quoteOptions(f).find((o) => o.value === v)?.label ?? v;
  if (f.type === "money") return inr(Number(v));
  return v;
}

let n = 0;
function changed(product: ProductId, id: string) {
  useQuote.setState({ last: { product, id, n: ++n } });
  const s = useQuote.getState();
  const q = quoteFor(product, s);
  emit("quote.changed", {
    product,
    field: id,
    answers: Object.entries(s.answers[product])
      .filter(([, v]) => v !== "")
      .map(([field, value]) => ({ field, value })),
    addons: s.addons[product],
    missing: q.missing,
    ...(q.complete ? { total: q.total } : {}),
  });
}

/** Put this product's builder in front. */
export function openQuote(product: ProductId) {
  if (useQuote.getState().product === product) return;
  useQuote.setState({ product });
}

/** Set one answer (raw text from an input: stored as typed, checked by the engine). */
export function setAnswer(product: ProductId, field: string, value: string) {
  const s = useQuote.getState();
  if (s.answers[product][field] === value) return;
  useQuote.setState({ answers: { ...s.answers, [product]: { ...s.answers[product], [field]: value } } });
  changed(product, field);
}

export function setAddon(product: ProductId, addon: string, on: boolean) {
  const s = useQuote.getState();
  const cur = s.addons[product];
  if (cur.includes(addon) === on) return;
  const spec = productById(product)!;
  const next = on ? spec.addons.map((a) => a.id).filter((id) => id === addon || cur.includes(id)) : cur.filter((x) => x !== addon);
  useQuote.setState({ addons: { ...s.addons, [product]: next } });
  changed(product, addon);
}

export function resetQuote(product: ProductId) {
  const s = useQuote.getState();
  useQuote.setState({
    answers: { ...s.answers, [product]: fieldDefaults(product) },
    addons: { ...s.addons, [product]: defaultAddons(product) },
  });
  changed(product, "reset");
}

/** The add-on's price with these answers, on or not (null until the quote is complete). */
export function addonImpact(product: ProductId, addon: string, s: QuoteState = useQuote.getState()): number | null {
  const ans = validAnswers(product, s.answers[product]);
  const withIt = quote(product, ans, [...s.addons[product].filter((x) => x !== addon), addon]);
  if (!withIt.complete) return null;
  return withIt.lines.find((l) => l.id === `addon:${addon}`)?.amount ?? null;
}

export const cityLabel = (v: string) => cities.find((c) => c.value === v)?.label ?? v;
