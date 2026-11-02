import { create } from "zustand";
import { persist } from "zustand/middleware";
import { type By, emit } from "../voice/events";
import { safeStorage } from "./storage";

interface ShortlistState {
  ids: string[];
  by: By;
  open: boolean;
  setOpen(open: boolean): void;
  toggle(id: string): void;
  set(ids: string[], by?: By): void;
}

export const useShortlist = create<ShortlistState>()(
  persist(
    (set, get) => ({
      ids: [],
      by: "visitor",
      open: false,
      setOpen: (open) => set({ open }),
      toggle(id) {
        const ids = get().ids.includes(id) ? get().ids.filter((x) => x !== id) : [...get().ids, id];
        set({ ids, by: "visitor" });
        emit("shortlist_changed", { product_ids: ids });
      },
      set(ids, by = "visitor") {
        set({ ids, by, open: by === "mira" ? true : get().open });
        if (by === "visitor") emit("shortlist_changed", { product_ids: ids });
      },
    }),
    { name: "fernhollow-shortlist", storage: safeStorage, partialize: (s) => ({ ids: s.ids }) },
  ),
);
