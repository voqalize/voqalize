import { create } from "zustand";
import { persist } from "zustand/middleware";
import { getProduct, getVariant } from "../data/catalog";
import { type By, type CartLine, emit } from "../voice/events";
import { safeStorage } from "./storage";

export interface Line extends CartLine {
  /** Who put it there, for the Emily tag. */
  by?: By;
}

interface CartState {
  lines: Line[];
  open: boolean;
  setOpen(open: boolean): void;
  add(lines: CartLine[], by?: By): void;
  setQty(productId: string, variantId: string, qty: number, by?: By): void;
  remove(productId: string, variantId: string, by?: By): void;
  replace(lines: Line[], by?: By, quiet?: boolean): void;
  clear(): void;
}

export function priced<T extends CartLine>(lines: T[]) {
  let total = 0;
  let saved = 0;
  const rows = lines.flatMap((l) => {
    const p = getProduct(l.product_id);
    if (!p) return [];
    const v = getVariant(p, l.variant_id);
    total += v.price * l.qty;
    if (v.compareAtPrice && v.compareAtPrice > v.price) saved += (v.compareAtPrice - v.price) * l.qty;
    return [{ line: l, product: p, variant: v }];
  });
  return { rows, total: Math.round(total * 100) / 100, saved: Math.round(saved * 100) / 100 };
}

const plain = (lines: Line[]): CartLine[] => lines.map(({ product_id, variant_id, qty }) => ({ product_id, variant_id, qty }));

function report(lines: Line[], by: By) {
  emit("cart_changed", { lines: plain(lines), total: priced(lines).total }, by);
}

export const useCart = create<CartState>()(
  persist(
    (set, get) => ({
      lines: [],
      open: false,
      setOpen: (open) => set({ open }),
      add(add, by = "visitor") {
        const lines = [...get().lines];
        for (const a of add) {
          const i = lines.findIndex((l) => l.product_id === a.product_id && l.variant_id === a.variant_id);
          if (i >= 0) lines[i] = { ...lines[i], qty: Math.min(99, lines[i].qty + a.qty), by };
          else lines.push({ ...a, by });
        }
        set({ lines, open: true });
        report(lines, by);
      },
      setQty(productId, variantId, qty, by = "visitor") {
        const lines = get()
          .lines.map((l) => (l.product_id === productId && l.variant_id === variantId ? { ...l, qty: Math.max(0, Math.min(99, qty)), by } : l))
          .filter((l) => l.qty > 0);
        set({ lines });
        report(lines, by);
      },
      remove(productId, variantId, by = "visitor") {
        const lines = get().lines.filter((l) => !(l.product_id === productId && l.variant_id === variantId));
        set({ lines });
        report(lines, by);
      },
      replace(lines, by = "emily", quiet = false) {
        set({ lines: lines.map((l) => ({ ...l, by })) });
        if (!quiet) report(lines, by);
      },
      clear: () => set({ lines: [] }),
    }),
    { name: "fernhollow-cart", storage: safeStorage, partialize: (s) => ({ lines: s.lines }) },
  ),
);
