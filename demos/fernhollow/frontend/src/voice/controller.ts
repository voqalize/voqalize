/**
 * The one controller every voice-driven surface goes through.
 *
 * Each brain → UI command in CONTRACT.md is a method here with the same name
 * and payload. The voice layer is a thin adapter (`dispatch(command, payload)`),
 * the `?debug=1` console calls the same methods by hand, and the shop's own
 * buttons call them too, with `by: "visitor"` — so every surface Emily can drive
 * is also one a shopper can drive by click, and both paths render through the
 * same component.
 *
 * Things Emily changed carry a "Emily" tag (`marks`). A change that moves
 * something already on screen is preceded by a 300 ms spotlight ring on the
 * target (`ring`). `undo` reverts the last screen-changing command.
 */
import { create } from "zustand";
import { type ContractFilters, getProduct, matchContractFilters } from "../data/catalog";
import { useCart } from "../state/cart";
import { useShortlist } from "../state/shortlist";
import { useSelection } from "./circle";
import { CHECKOUT_FIELDS, CHECKOUT_STEPS, type CheckoutField, type CheckoutStep, STEP_OF_FIELD, placeOrder, useCheckout } from "../state/checkout";
import { type By, type CartLine, emit } from "./events";
import { totalOf } from "./local";
import type { Brief, CommandName, Commands, CompareRow, Piece, Swap } from "./types";

export interface Listing {
  title: string;
  query: string;
  ids: string[];
  count: number;
  filters: ContractFilters | null;
  assumption: string | null;
  by: By;
}

export interface RoomBoard {
  room: string;
  budget: number;
  total: number;
  pieces: Piece[];
  savings: Swap[];
  saved: number;
  movedTo: string | null;
  /** Slots Emily just changed, for the tag and the arrival animation. */
  changed: string[];
  by: By;
  /** Bumps on every new set, so the tiles replay their one-by-one entrance. */
  version: number;
}

export interface Compare {
  ids: string[];
  rows: CompareRow[];
  summary: string;
  by: By;
}

export interface Strip<T> {
  anchorId: string;
  items: T[];
  by: By;
}

export interface Spotlight {
  target: string;
  stamp: number;
}

interface Snapshot {
  path: string;
  slice: Partial<EmilyState>;
  cart: CartLine[];
  shortlist: string[];
}

export interface EmilyState {
  brief: (Brief & { productsLeft: number; by: By }) | null;
  listing: Listing | null;
  board: RoomBoard | null;
  compare: Compare | null;
  goesWith: Strip<{ product_id: string; reason: string }> | null;
  moreLike: Strip<{ product_id: string; differences: string[] }> | null;
  confirm: (Commands["confirm_add"] & { by: By }) | null;
  suggestion: Commands["suggest_finish"] | null;
  policy: string | null;
  spotlight: Spotlight | null;
  /** Variant chosen per product by a command (the product page follows it). */
  variants: Record<string, { id: string; by: By; stamp: number }>;
  /** Product page section to ring after open_product. */
  focus: { productId: string; section: string; stamp: number } | null;
  /** Keys of things Emily changed: "filters", "variant:<id>", "cart", "board", "compare"… */
  marks: Record<string, number>;
  history: Snapshot[];
  /** Numbered products Emily asked the shopper to pick between. */
  choices: { ids: string[]; label: string } | null;
}

const SLICE_KEYS = ["brief", "listing", "board", "compare", "goesWith", "moreLike", "suggestion", "policy", "variants"] as const;

export const useEmily = create<EmilyState>(() => ({
  brief: null,
  listing: null,
  board: null,
  compare: null,
  goesWith: null,
  moreLike: null,
  confirm: null,
  suggestion: null,
  policy: null,
  spotlight: null,
  variants: {},
  focus: null,
  marks: {},
  history: [],
  choices: null,
}));

const set = useEmily.setState;
const get = useEmily.getState;

// ── Router seam ───────────────────────────────────────────────────────────

type Navigate = (path: string) => void;
let navigateFn: Navigate = (path) => {
  window.history.pushState({}, "", `${import.meta.env.BASE_URL.replace(/\/$/, "")}${path}`);
};
let currentPath = () => window.location.pathname.replace(import.meta.env.BASE_URL.replace(/\/$/, ""), "") || "/";

/** The router hands its navigate function here once, at mount. */
export function bindRouter(navigate: Navigate, path: () => string) {
  navigateFn = navigate;
  currentPath = path;
}

const go = (path: string) => {
  if (currentPath() !== path) navigateFn(path);
};

// ── Helpers ───────────────────────────────────────────────────────────────

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const reduced = () => {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
};

/** Ring a target for 300 ms before the change lands. Resolves at once if it is not on screen. */
export async function ring(target: string): Promise<void> {
  set({ spotlight: { target, stamp: Date.now() } });
  const el = document.querySelector(`[data-spot="${CSS.escape(target)}"]`);
  if (!el) return;
  const box = el.getBoundingClientRect();
  if (box.bottom < 0 || box.top > window.innerHeight) el.scrollIntoView({ block: "center", behavior: reduced() ? "auto" : "smooth" });
  await wait(300);
}

function mark(...keys: string[]) {
  const now = Date.now();
  set((s) => ({ marks: { ...s.marks, ...Object.fromEntries(keys.map((k) => [k, now])) } }));
}
const unmark = (...keys: string[]) =>
  set((s) => {
    const marks = { ...s.marks };
    keys.forEach((k) => delete marks[k]);
    return { marks };
  });

let emilyActedAt = 0;
/** Who caused the page change that is landing now: Emily if she acted in the last moment. */
export const navigatedBy = (): By => (Date.now() - emilyActedAt < 1500 ? "emily" : "visitor");

/** Remember the screen before a change, so `undo` can put it back. */
function snapshot() {
  emilyActedAt = Date.now();
  const s = get();
  const slice = Object.fromEntries(SLICE_KEYS.map((k) => [k, s[k]])) as Partial<EmilyState>;
  const snap: Snapshot = {
    path: currentPath(),
    slice,
    cart: useCart.getState().lines,
    shortlist: useShortlist.getState().ids,
  };
  set({ history: [...s.history.slice(-19), snap] });
}

const isEmily = (by: By) => by === "emily";

/** Bring checkout on screen before filling it. */
async function toCheckout() {
  if (currentPath() === "/checkout") return;
  go("/checkout");
  await wait(350);
}

/** Bring the room board on screen before changing it. */
async function toBoard() {
  if (currentPath() === "/board") return;
  go("/board");
  await wait(350);
}

// ── Commands (names and payloads mirror CONTRACT.md) ──────────────────────

export const emily = {
  navigate({ page }: Commands["navigate"], by: By = "emily") {
    if (isEmily(by)) snapshot();
    const clean = page.replace(/^\/+/, "");
    if (clean === "home" || clean === "") return go("/");
    if (clean.startsWith("policy/")) {
      const topic = clean.slice("policy/".length);
      return go(topic === "about" ? "/about" : topic === "faq" ? "/faq" : `/policy/${topic}`);
    }
    go(`/${clean}`);
  },

  show_products(p: Commands["show_products"], by: By = "emily") {
    if (isEmily(by)) snapshot();
    set({ listing: { title: p.title, query: p.query, ids: p.product_ids, count: p.count, filters: null, assumption: null, by } });
    if (isEmily(by)) mark("listing");
    go("/picks");
  },

  apply_filters(p: Commands["apply_filters"], by: By = "emily") {
    if (isEmily(by)) snapshot();
    const prev = get().listing;
    set({
      listing: {
        title: prev?.title ?? "Picked for you",
        query: prev?.query ?? "",
        ids: p.product_ids,
        count: p.count,
        filters: p.filters,
        assumption: p.assumption ?? null,
        by,
      },
    });
    if (isEmily(by)) mark("filters");
    else emit("filter_changed", { filters: p.filters as Record<string, unknown> });
    go("/picks");
  },

  async remove_filter(p: Commands["remove_filter"], by: By = "emily") {
    const listing = get().listing;
    if (!listing?.filters) return;
    if (isEmily(by)) {
      snapshot();
      await ring(`filter:${p.key}`);
    }
    const filters = withoutFilter(listing.filters, p.key);
    set({ listing: { ...listing, filters, ids: p.product_ids, count: p.count, by } });
    if (!isEmily(by)) emit("filter_changed", { filters: filters as Record<string, unknown> });
  },

  /** The click path for a chip: recompute the list locally, then remove. */
  removeFilterByHand(key: string) {
    const listing = get().listing;
    if (!listing?.filters) return;
    const ids = matchContractFilters(withoutFilter(listing.filters, key)).map((x) => x.id);
    void emily.remove_filter({ key, product_ids: ids, count: ids.length }, "visitor");
  },

  open_product(p: Commands["open_product"], by: By = "emily") {
    if (isEmily(by)) snapshot();
    if (p.variant_id) set((s) => ({ variants: { ...s.variants, [p.product_id]: { id: p.variant_id!, by, stamp: Date.now() } } }));
    if (p.focus) set({ focus: { productId: p.product_id, section: p.focus, stamp: Date.now() } });
    if (isEmily(by) && p.variant_id) mark(`variant:${p.product_id}`);
    go(`/product/${p.product_id}`);
  },

  async select_variant(p: Commands["select_variant"], by: By = "emily") {
    if (isEmily(by)) {
      snapshot();
      await ring("section:options");
      mark(`variant:${p.product_id}`);
    } else unmark(`variant:${p.product_id}`);
    set((s) => ({ variants: { ...s.variants, [p.product_id]: { id: p.variant_id, by, stamp: Date.now() } } }));
    emit("variant_selected", { product_id: p.product_id, variant_id: p.variant_id }, by);
  },

  async highlight(p: Commands["highlight"]) {
    await ring(p.target);
  },

  update_brief(p: Commands["update_brief"], by: By = "emily") {
    if (isEmily(by)) snapshot();
    set({ brief: { ...p.brief, productsLeft: p.products_left, by } });
    if (isEmily(by)) mark("brief");
  },

  clearBrief() {
    set({ brief: null });
  },

  show_room_set(p: Commands["show_room_set"], by: By = "emily") {
    if (isEmily(by)) snapshot();
    const version = (get().board?.version ?? 0) + 1;
    set({
      board: {
        room: p.room,
        budget: p.budget,
        total: p.total,
        pieces: p.pieces,
        savings: [],
        saved: 0,
        movedTo: null,
        changed: [],
        by,
        version,
      },
    });
    if (isEmily(by)) mark("board");
    go("/board");
  },

  async swap_piece(p: Commands["swap_piece"], by: By = "emily") {
    const board = get().board;
    if (!board) return;
    if (isEmily(by)) {
      snapshot();
      await toBoard();
      await ring(`slot:${p.slot}`);
    }
    const pieces = board.pieces.map((x) => (x.slot === p.slot ? p.piece : x));
    set({
      board: {
        ...board,
        pieces,
        total: isEmily(by) ? p.total : totalOf(pieces),
        savings: board.savings.filter((s) => s.slot !== p.slot),
        changed: isEmily(by) ? [...new Set([...board.changed, p.slot])] : board.changed.filter((s) => s !== p.slot),
        by,
      },
    });
    if (!isEmily(by)) emit("room_board_edited", { slot: p.slot, action: "swap" });
  },

  removePiece(slot: string) {
    const board = get().board;
    if (!board) return;
    const pieces = board.pieces.filter((x) => x.slot !== slot);
    set({ board: { ...board, pieces, total: totalOf(pieces) } });
    emit("room_board_edited", { slot, action: "remove" });
  },

  setBudget(budget: number) {
    const board = get().board;
    if (board) set({ board: { ...board, budget } });
  },

  show_compare(p: Commands["show_compare"], by: By = "emily") {
    if (isEmily(by)) snapshot();
    set({ compare: { ids: p.product_ids, rows: p.rows, summary: p.summary, by } });
    if (isEmily(by)) mark("compare");
    go("/compare");
  },

  show_goes_with(p: Commands["show_goes_with"], by: By = "emily") {
    if (isEmily(by)) snapshot();
    set({ goesWith: { anchorId: p.anchor_id, items: p.items, by } });
    if (isEmily(by)) {
      mark("goes-with");
      go(`/product/${p.anchor_id}`);
      setTimeout(() => void ring("section:goes-with"), 60);
    }
  },

  show_more_like(p: Commands["show_more_like"], by: By = "emily") {
    if (isEmily(by)) snapshot();
    set({ moreLike: { anchorId: p.anchor_id, items: p.items, by } });
    if (isEmily(by)) {
      mark("more-like");
      go(`/product/${p.anchor_id}`);
      setTimeout(() => void ring("section:more-like"), 60);
    }
  },

  async show_savings(p: Commands["show_savings"], by: By = "emily") {
    const board = get().board;
    if (!board) return;
    if (isEmily(by)) {
      snapshot();
      await toBoard();
      await ring("section:budget");
    }
    // A saving is a swap: the cheaper piece takes the slot, and its tile shows was/now.
    const pieces = board.pieces.map((piece) => {
      const swap = p.swaps.find((s) => s.slot === piece.slot);
      const next = swap && getProduct(swap.to_id);
      if (!swap || !next) return piece;
      const v = next.variants[0];
      return { ...piece, product_id: next.id, variant_id: v.id, title: next.title, price: swap.now, compare_at: v.compareAtPrice, image: next.images[0] };
    });
    set({
      board: {
        ...board,
        pieces,
        total: totalOf(pieces),
        savings: p.swaps,
        saved: p.saved,
        movedTo: p.moved_to ?? null,
        changed: isEmily(by) ? [...new Set([...board.changed, ...p.swaps.map((s) => s.slot)])] : board.changed,
        by,
      },
    });
    if (isEmily(by)) mark("savings");
    else p.swaps.forEach((s) => emit("room_board_edited", { slot: s.slot, action: "save" }));
  },

  update_shortlist(p: Commands["update_shortlist"], by: By = "emily") {
    if (isEmily(by)) {
      snapshot();
      mark("shortlist");
    }
    useShortlist.getState().set(p.product_ids, by);
  },

  async confirm_add(p: Commands["confirm_add"], by: By = "emily") {
    if (isEmily(by)) await ring("button:add-to-cart");
    set({ confirm: { ...p, by } });
  },

  /** The shopper's answer to a confirm prompt. */
  answerConfirm(confirmed: boolean) {
    const c = get().confirm;
    if (!c) return;
    set({ confirm: null });
    if (confirmed) useCart.getState().add(c.lines, "visitor");
    emit("confirm_result", { confirmed });
  },

  cart_updated(p: Commands["cart_updated"], by: By = "emily") {
    if (isEmily(by)) {
      snapshot();
      mark("cart");
    }
    useCart.getState().replace(p.lines, by, true);
    useCart.getState().setOpen(true);
  },

  suggest_finish(p: Commands["suggest_finish"]) {
    set({ suggestion: p });
    useCart.getState().setOpen(true);
  },

  dismissSuggestion() {
    set({ suggestion: null });
  },

  open_policy(p: Commands["open_policy"]) {
    set({ policy: p.topic });
  },

  closePolicy() {
    set({ policy: null });
  },

  // ── v2: checkout, choices ──

  async checkout_fill(p: Commands["checkout_fill"]) {
    const field = p.field as CheckoutField;
    if (!(CHECKOUT_FIELDS as readonly string[]).includes(field)) {
      console.info(`[fernhollow] checkout has no field ${p.field}`);
      return;
    }
    if (!useCart.getState().lines.length) {
      console.info("[fernhollow] checkout_fill with an empty cart");
      return;
    }
    await toCheckout();
    const step = STEP_OF_FIELD[field];
    if (useCheckout.getState().step !== step) {
      useCheckout.getState().setStep(step, "emily");
      await wait(160);
    }
    await ring(`field:${field}`);
    useCheckout.getState().set(field, p.value, "emily");
  },

  async checkout_step(p: Commands["checkout_step"]) {
    if (!(CHECKOUT_STEPS as readonly string[]).includes(p.step) || !useCart.getState().lines.length) return;
    await toCheckout();
    useCheckout.getState().setStep(p.step as CheckoutStep, "emily");
    window.scrollTo({ top: 0 });
  },

  async confirm_place_order(p: Commands["confirm_place_order"]) {
    if (!useCart.getState().lines.length) return;
    await toCheckout();
    if (useCheckout.getState().step !== "review") {
      useCheckout.getState().setStep("review", "emily");
      await wait(160);
    }
    await ring("button:place-order");
    useCheckout.setState({ confirm: { total: p.total, label: p.label } });
  },

  async order_placed(p: Commands["order_placed"]) {
    const order = placeOrder(p.order_number);
    if (!order) return;
    go("/checkout/confirmation");
    await wait(60);
    useCart.getState().clear();
  },

  async show_choices(p: Commands["show_choices"]) {
    const ids = p.product_ids.slice(0, 4);
    set({ choices: { ids, label: p.label } });
    const first = document.querySelector(`[data-spot="product:${CSS.escape(ids[0] ?? "")}"]`);
    if (first) {
      const r = first.getBoundingClientRect();
      if (r.top < 80 || r.bottom > window.innerHeight) first.scrollIntoView({ block: "center", behavior: reduced() ? "auto" : "smooth" });
    }
  },

  clear_choices() {
    set({ choices: null });
  },

  clear_selection() {
    useSelection.getState().clear("emily");
  },

  /** The shopper clicked a numbered card. */
  choiceMade(productId: string) {
    if (!get().choices?.ids.includes(productId)) return;
    set({ choices: null });
    emit("choice_made", { product_id: productId });
  },

  undo() {
    const history = get().history;
    const last = history[history.length - 1];
    if (!last) return;
    set({ ...last.slice, history: history.slice(0, -1), confirm: null });
    useCart.getState().replace(last.cart, "visitor", true);
    useShortlist.setState({ ids: last.shortlist });
    go(last.path);
  },
};

function withoutFilter(f: ContractFilters, key: string): ContractFilters {
  // A key is a field ("on_sale", "price") or a field and a word ("materials:oak").
  const [field, word] = key.split(":");
  const next: ContractFilters = { ...f };
  if (field === "price") {
    next.price_min = null;
    next.price_max = null;
  } else if ((field === "materials" || field === "colours" || field === "styles") && word) {
    next[field] = (f[field] ?? []).filter((w) => w.toLowerCase() !== word.toLowerCase());
  } else if (field === "materials" || field === "colours" || field === "styles") {
    next[field] = [];
  } else if (field in next) {
    (next as Record<string, unknown>)[field] = null;
  }
  return next;
}

/** The voice adapter: one ui-command off the wire → one method. Unknown commands are ignored. */
export function dispatch(command: string, payload: unknown): boolean {
  const fn = (emily as unknown as Record<string, ((p: unknown, by?: By) => unknown) | undefined>)[command];
  if (!fn || !isCommand(command)) {
    console.info(`[fernhollow] ignoring unknown command ${command}`);
    return false;
  }
  void fn(payload ?? {}, "emily");
  return true;
}

const COMMANDS = new Set<string>([
  "navigate", "show_products", "apply_filters", "remove_filter", "open_product", "select_variant", "highlight",
  "update_brief", "show_room_set", "swap_piece", "show_compare", "show_goes_with", "show_more_like", "show_savings",
  "update_shortlist", "confirm_add", "cart_updated", "suggest_finish", "open_policy", "undo",
  "checkout_fill", "checkout_step", "confirm_place_order", "order_placed", "show_choices", "clear_choices", "clear_selection",
]);
const isCommand = (c: string): c is CommandName => COMMANDS.has(c);

/** True while a Emily mark is fresh enough to show its tag. */
export const MARK_MS = 1000 * 60 * 10;
export function useMarked(key: string): boolean {
  return useEmily((s) => {
    const t = s.marks[key];
    return t != null && Date.now() - t < MARK_MS;
  });
}
