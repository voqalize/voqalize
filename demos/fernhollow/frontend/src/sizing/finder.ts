/**
 * The size guide's finder, evaluated exactly as backend/sizing.py does, over
 * the same content/size_guide.json: the next question is the first whose
 * `when` holds and is unanswered; the size is the first rule whose `if` all
 * hold. A size is picked only for beds and bedding (Queen/King) and vases and
 * faux stems (Small/Large); rugs and curtains get placement advice.
 */
import { create } from "zustand";
import guideJson from "../../../content/size_guide.json";
import { type Product, type Variant, products } from "../data/catalog";
import type { By } from "../voice/events";

export interface Option {
  value: string;
  label: string;
}
export interface Question {
  id: string;
  label: string;
  when?: Record<string, string>;
  options: Option[];
}
interface Rule {
  if: Record<string, string>;
  size: string;
  why: string;
}
export interface Section {
  id: "beds" | "vases" | "rugs" | "curtains";
  title: string;
  categories: string[];
  note?: string;
  sizes?: { size: string; standard?: string; suits: string }[];
  layouts?: { id: string; label: string; text: string }[];
  drops?: { id: string; label: string; text: string }[];
  rules: string[];
}
export interface Guide {
  title: string;
  intro: string;
  sections: Section[];
  finder: { questions: Question[]; rules: Rule[] };
}

export const GUIDE = guideJson as unknown as Guide;
export const QUESTIONS = GUIDE.finder.questions;
export type Answers = Record<string, string>;

export interface Advice {
  size: string | null;
  why: string;
  section: Section["id"];
}

const holds = (when: Record<string, string> | undefined, a: Answers) => Object.entries(when ?? {}).every(([k, v]) => a[k] === v);

export const question = (id: string) => QUESTIONS.find((q) => q.id === id);
export const section = (id: string) => GUIDE.sections.find((s) => s.id === id);

/** The questions that apply now, in order: answered ones and the next one. */
export function asked(a: Answers): Question[] {
  return QUESTIONS.filter((q) => holds(q.when, a));
}

export function nextQuestion(a: Answers): Question | null {
  return QUESTIONS.find((q) => !(q.id in a) && holds(q.when, a)) ?? null;
}

export function advise(a: Answers): Advice | null {
  const kind = a.kind;
  for (const r of GUIDE.finder.rules) {
    if (holds(r.if, a)) return { size: r.size, why: r.why, section: kind === "bed" ? "beds" : "vases" };
  }
  if (kind === "rug" && a.layout) {
    const item = section("rugs")?.layouts?.find((x) => x.id === a.layout);
    if (item) return { size: null, why: `${item.label}: ${item.text}`, section: "rugs" };
  }
  if (kind === "curtains" && a.drop) {
    const item = section("curtains")?.drops?.find((x) => x.id === a.drop);
    if (item) return { size: null, why: `${item.label}: ${item.text}`, section: "curtains" };
  }
  return null;
}

/** Answering one question: `kind` starts over; any other answer drops the
 *  answers that no longer apply (a new mattress clears sleepers and room). */
export function answer(a: Answers, id: string, value: string): Answers {
  if (id === "kind") return { kind: value };
  const next: Answers = { ...a, [id]: value };
  let changed = true;
  while (changed) {
    changed = false;
    for (const q of QUESTIONS) {
      if (q.id in next && !holds(q.when, next)) {
        delete next[q.id];
        changed = true;
      }
    }
  }
  return next;
}

export const valid = (id: string, value: string) => !!question(id)?.options.some((o) => o.value === value);

const sizeOf = (p: Product) => p.options.find((o) => o.name === "Size")?.values ?? [];
const KIND_SECTION: Record<string, Section["id"]> = { bed: "beds", vase: "vases", rug: "rugs", curtains: "curtains" };
export const sectionOfKind = (kind: string | undefined) => (kind ? KIND_SECTION[kind] : undefined);

/** A section's products with the variant in `size` (else the first), cheapest first. */
export function sizedProducts(sectionId: string, size: string | null = null): { p: Product; v: Variant }[] {
  const s = section(sectionId);
  if (!s) return [];
  const out: { p: Product; v: Variant }[] = [];
  for (const cat of s.categories) {
    for (const p of products) {
      if (p.categorySlug !== cat) continue;
      if ((sectionId === "beds" || sectionId === "vases") && !sizeOf(p).length) continue;
      // A piece that does not come in the picked size is not shown for it
      // (a throw sold Small/Large sits among the Queen/King bedding).
      if (size && sizeOf(p).length && !sizeOf(p).includes(size)) continue;
      const v = (size && p.variants.find((x) => x.options.Size === size)) || p.variants[0];
      out.push({ p, v });
    }
  }
  return out.sort((a, b) => a.v.price - b.v.price || (a.p.id < b.p.id ? -1 : a.p.id > b.p.id ? 1 : 0));
}

/** The finder as the page holds it; `changed` names the last answer and who gave it. */
export const useSizeFinder = create<{
  answers: Answers;
  changed: { question: string; value: string; by: By; stamp: number } | null;
  set(id: string, value: string, by?: By): void;
  reset(): void;
}>((set, get) => ({
  answers: {},
  changed: null,
  set(id, value, by = "visitor") {
    set({ answers: answer(get().answers, id, value), changed: { question: id, value, by, stamp: Date.now() } });
  },
  reset: () => set({ answers: {}, changed: null }),
}));
