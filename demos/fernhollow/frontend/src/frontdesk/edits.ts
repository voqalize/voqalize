/**
 * The gift edit and the showroom kiosk: their authored controls
 * (content/gift_guide.json, content/kiosk.json) and their ranked lists, which
 * come only from backend/data/edits.json — the file the brain reads too, so
 * what is said is what is shown. That file is loaded lazily, on the pages
 * that need it.
 */
import { useEffect, useState } from "react";
import { create } from "zustand";
import giftJson from "../../../content/gift_guide.json";
import kioskJson from "../../../content/kiosk.json";
import type { By } from "../voice/events";

export interface Pick {
  product_id: string;
  variant_id: string;
  reason: string;
}
interface Edits {
  gifts: Record<string, Pick[]>;
  kiosk: Record<string, Pick[]>;
}

export const GIFTS = giftJson as unknown as {
  picks: number;
  budgets: number[];
  recipients: { id: string; label: string }[];
  occasions: { id: string; label: string }[];
};

export interface KioskOption {
  value: string;
  label: string;
  line?: string;
  max?: number | null;
}
export const KIOSK = kioskJson as unknown as {
  headline: string;
  attract: string;
  picks: number;
  questions: { id: "room" | "feel" | "budget"; label: string; options: KioskOption[] }[];
};

let loading: Promise<Edits> | null = null;
let loaded: Edits | null = null;
export function loadEdits(): Promise<Edits> {
  loading ??= import("../../../backend/data/edits.json").then((m) => {
    loaded = (m.default ?? m) as unknown as Edits;
    return loaded;
  });
  return loading;
}

/** The edits, once loaded (null until then). */
export function useEdits(): Edits | null {
  const [e, setE] = useState<Edits | null>(loaded);
  useEffect(() => {
    if (!e) void loadEdits().then(setE);
  }, [e]);
  return e;
}

export const giftKey = (r: string, o: string, b: number) => `${r}|${o}|${b}`;
export const kioskKey = (room: string, feel: string, budget: string) => `${room}|${feel}|${budget}`;

// ── The gift edit's controls ────────────────────────────────────────────────

export type GiftControl = "recipient" | "occasion" | "budget";
/**
 * The gift edit's controls. Nothing is chosen until the shopper (or the
 * agent, for them) chooses it (owner, round 1, F7). A budget of 0 is
 * "No limit"; `null` is not chosen yet.
 */
export interface GiftState {
  recipient: string | null;
  occasion: string | null;
  budget: number | null;
  changed: { by: By; stamp: number } | null;
  set(patch: Partial<Pick3>, by?: By): void;
  reset(): void;
}
type Pick3 = { recipient: string | null; occasion: string | null; budget: number | null };

/** The budget chips the page offers: the authored ones, then No limit (0). */
export const BUDGET_CHIPS: number[] = [...GIFTS.budgets, 0];
export const budgetLabel = (b: number) => (b === 0 ? "No limit" : `Up to $${b}`);

export const useGifts = create<GiftState>((set) => ({
  recipient: null,
  occasion: null,
  budget: null,
  changed: null,
  set(patch, by = "visitor") {
    set({ ...patch, changed: { by, stamp: Date.now() } });
  },
  reset: () => set({ recipient: null, occasion: null, budget: null, changed: null }),
}));

// ── The kiosk ───────────────────────────────────────────────────────────────

export type KioskScreen = "attract" | "room" | "feel" | "budget" | "picks";
export type KioskAnswers = Partial<Record<"room" | "feel" | "budget", string>>;
const ORDER: KioskScreen[] = ["room", "feel", "budget", "picks"];

export const useKiosk = create<{
  screen: KioskScreen;
  answers: KioskAnswers;
  changed: { question: string; value: string; by: By; stamp: number } | null;
  start(by?: By): void;
  answer(question: "room" | "feel" | "budget", value: string, by?: By): void;
  go(screen: KioskScreen): void;
  restart(by?: By): void;
}>((set, get) => ({
  screen: "attract",
  answers: {},
  changed: null,
  start() {
    if (get().screen === "attract") set({ screen: "room" });
  },
  answer(question, value, by = "visitor") {
    const answers = { ...get().answers, [question]: value };
    // The next question not yet answered, or the picks.
    const screen = ORDER.find((s) => s === "picks" || !(s in answers)) ?? "picks";
    set({ answers, screen, changed: { question, value, by, stamp: Date.now() } });
  },
  go: (screen) => set({ screen }),
  restart: () => set({ screen: "attract", answers: {}, changed: null }),
}));

export const kioskOption = (question: string, value: string | undefined) =>
  KIOSK.questions.find((q) => q.id === question)?.options.find((o) => o.value === value);
