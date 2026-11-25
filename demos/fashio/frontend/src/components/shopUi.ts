/** The listing's own UI state that a move may need to change: the brand list expanded, the page of results. */
import { create } from "zustand";

export const useShopUi = create<{ allBrands: boolean; brandQuery: string; page: number }>(() => ({ allBrands: false, brandQuery: "", page: 0 }));

/** Results per page: the grid never draws more than this at once. */
export const PAGE_SIZE = 48;
