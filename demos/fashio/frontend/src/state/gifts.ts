/**
 * The gift finder's page state: the brief (nothing chosen until the shopper,
 * or the agent on their word, sets it) and the shortlist on screen with a
 * reason per card. "Show gift ideas" by hand runs `pickGifts`; on a call the
 * brain picks and sends `gifts.show` with its own reasons.
 */
import { create } from "zustand";
import { typeLabel } from "../data/catalog";
import { type GiftBrief, giftReason, pickGifts } from "../data/gifts";

export interface GiftShown {
  ids: number[];
  reasons: string[];
  /** The brief the list was made for (to say when the brief moved on). */
  brief: string;
}

interface GiftStore {
  brief: GiftBrief;
  /** "No limit" was chosen (budget_max stays absent, but the field is answered). */
  noLimit: boolean;
  shown: GiftShown | null;
  setBrief: (patch: Partial<GiftBrief>) => void;
  setNoLimit: (on: boolean) => void;
  toggleIn: (field: "colours" | "patterns", value: string) => void;
  show: (ids: number[], reasons: string[]) => void;
  /** Run the pick by hand. Returns how many were found. */
  showByHand: () => number;
  reset: () => void;
}

export const briefKey = (b: GiftBrief) => JSON.stringify([b.recipient, b.occasion, b.budget_max, b.size, b.colours, b.patterns, b.material]);

const clean = (b: GiftBrief): GiftBrief => {
  const out: GiftBrief = {};
  if (b.recipient) out.recipient = b.recipient;
  if (b.occasion) out.occasion = b.occasion;
  if (b.budget_max) out.budget_max = b.budget_max;
  if (b.size) out.size = b.size;
  if (b.colours?.length) out.colours = b.colours;
  if (b.patterns?.length) out.patterns = b.patterns;
  if (b.material) out.material = b.material;
  return out;
};

export const useGifts = create<GiftStore>((set, get) => ({
  brief: {},
  noLimit: false,
  shown: null,
  setBrief: (patch) => {
    const brief = clean({ ...get().brief, ...patch });
    set({ brief, noLimit: brief.budget_max ? false : get().noLimit });
  },
  setNoLimit: (noLimit) => set({ noLimit, brief: noLimit ? clean({ ...get().brief, budget_max: undefined }) : get().brief }),
  toggleIn: (field, value) => {
    const now = get().brief[field] ?? [];
    const next = now.includes(value) ? now.filter((x) => x !== value) : [...now, value];
    get().setBrief({ [field]: next });
  },
  show: (ids, reasons) => set({ shown: { ids, reasons, brief: briefKey(get().brief) } }),
  showByHand: () => {
    const b = get().brief;
    const picks = pickGifts(b);
    get().show(
      picks.map((p) => p.id),
      picks.map((p) => giftReason(p, b, typeLabel)),
    );
    return picks.length;
  },
  reset: () => set({ brief: {}, noLimit: false, shown: null }),
}));
