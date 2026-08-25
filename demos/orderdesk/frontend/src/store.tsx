/**
 * Shared state for the OrderDesk demo — the pharmacist's phone and the voice call
 * drive one store, so the agent and the pharmacist edit the same cart.
 *
 * Two bridges, the travel/sugar pattern:
 *   - the brain's `ui_command`s land on {@link OrderDeskStore.uiCommands}, a map
 *     typed against `OrderDeskCommands` (`uiCommands.ts`, mirroring brain.py) —
 *     line items appear as free text, resolve, and settle on a SKU;
 *   - `snapshot()` goes back out as `state_sync` (`{ screen: OrderSnapshot }`) on
 *     every `rev` bump, so the agent's grounding always shows the *authoritative*
 *     cart — including everything the pharmacist tapped by hand (a variant pill,
 *     a quantity, a delete, a manual search add, Confirm).
 *
 * The cart is keyed by line-item id: the brain numbers its own rows (`li1`…) and
 * re-sends each row's full render state, which this store diffs in by id; rows the
 * pharmacist adds from the search bar are numbered `m1`… on this side.
 *
 * Navigation (picker → push notification → live call → ended) is React state, so
 * the call survives every screen change.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { buildBrainPayload, pharmacyById, scenarioById } from "./data";
import { CLIENT_MESSAGE, type OrderDeskCommands } from "./uiCommands";
import type {
  DisambigChoice,
  FamilyWire,
  LineItemView,
  OrderSnapshot,
  Pharmacy,
  Phase,
  Scenario,
  SkuWire,
} from "./types";

type AgentSend = ((type: string, data: unknown) => void) | null;

/** One handler per wire name in `T`, typed to that action's payload. */
type UiCommandHandlers<T> = { [K in keyof T]: (args: T[K]) => void };

/**
 * A line item as this screen holds it: the brain's render state plus the two
 * things only the browser knows — whether a tap on this screen locked the row
 * (so a late, stale agent upsert cannot un-lock it), and a nonce that re-triggers
 * the row's entry animation when it changes.
 */
export interface LineItem extends LineItemView {
  pinned: boolean;
  nonce: number;
  /**
   * The `question.text` the pharmacist has already answered by tapping a pill.
   * A late agent `upsert_items` still carrying that same question over the *wider*
   * candidate set is a stale echo of the tap and is dropped, so a narrowing never
   * flickers back open. The agent's NEXT question (new text, or the same text over
   * a subset) lands normally.
   */
  answered: string | null;
}

/** The row the agent is asking about right now (`highlight_item`). */
export interface HighlightState {
  id: string;
  note: string | null;
  nonce: number;
}

/**
 * The inline "Change variant" strip, open on exactly one matched row at a time.
 * Opening sends `list_variants`; `show_variants` fills it in. It is a *browse*,
 * not a question — the pharmacist asked to see the siblings — so it is capped by
 * scrolling rather than by `PILL_CAP`, and it never speaks or infers.
 */
export interface VariantStrip {
  itemId: string;
  family: string;
  results: SkuWire[];
  differingAxes: string[];
  /** Waiting on `show_variants`; the strip shows a placeholder line meanwhile. */
  loading: boolean;
}

interface OrderDeskStore {
  // ── Navigation ────────────────────────────────────────────────────────────
  phase: Phase;
  scenario: Scenario | null;
  pharmacy: Pharmacy | null;
  /** The exact PHARMACY CONTEXT payload for this call (also shown to the audience). */
  brainPayload: () => unknown;
  startScenario: (scenarioId: string) => void;
  acceptCall: () => void;
  declineCall: () => void;
  endCall: () => void;
  backToPicker: () => void;

  // ── The cart ──────────────────────────────────────────────────────────────
  items: LineItem[];
  /** One-line banner from the agent (`order_note`), until replaced or dismissed. */
  note: string | null;
  dismissNote: () => void;
  highlight: HighlightState | null;
  confirmed: boolean;
  orderNo: string | null;

  /** Rows that keep Confirm disabled — unresolved, or resolved with no quantity. */
  blockedIds: string[];
  canConfirm: boolean;
  /** Order value at PTR — the number a pharmacist actually cares about. */
  totalPtr: number;

  // ── Manual edits (each bumps `rev`, so the agent hears about it) ───────────
  /** Tap a variant pill: promote the row to `matched` on the SkuWire it already holds. */
  choosePill: (itemId: string, sku: SkuWire) => void;
  /**
   * Tap a pill on the agent's disambiguation question (DESIGN §7-bis). Local-first:
   * a leaf answers the row outright, a group narrows the candidate set on this
   * screen and — when few enough remain — grows the leaf pills here, without a
   * round trip. Either way `rev` bumps, so `state_sync` tells the agent what the
   * pharmacist just pointed at (`candidate_codes`).
   */
  chooseChoice: (itemId: string, choice: DisambigChoice) => void;
  /**
   * Tap a family card the browser holds whole ({@link familyHeldWhole}): narrow
   * this row's candidates to that family, right here — no round trip. The local
   * twin of {@link chooseChoice}.
   */
  narrowToFamily: (itemId: string, family: string) => void;
  /**
   * Open the search panel scoped to a family, for this row — the fallback for a
   * family whose SKUs this screen does *not* hold whole, and the escape hatch
   * behind every "+N more" pill.
   */
  chooseFamily: (itemId: string, family: string) => void;
  setQuantity: (itemId: string, quantity: number) => void;
  removeItem: (itemId: string) => void;
  confirmOrder: () => void;

  // ── Inline variant edit (list_variants → show_variants) ────────────────────
  /** The one row whose variant strip is open, or null. */
  variantStrip: VariantStrip | null;
  /** "Change variant" on a matched row: ask the brain for the family's siblings. */
  openVariants: (itemId: string, family: string) => void;
  closeVariants: () => void;
  /** Pick a sibling: re-lock the row on it, keeping the quantity already ordered. */
  pickVariant: (itemId: string, sku: SkuWire) => void;

  // ── Manual search (catalog_search → show_search_results) ───────────────────
  searchQuery: string;
  searchResults: SkuWire[];
  searching: boolean;
  searchOpen: boolean;
  /** Set when the panel is picking a SKU *for* a row rather than adding a new one. */
  searchTarget: string | null;
  setSearchQuery: (query: string) => void;
  closeSearch: () => void;
  /** Tap a search result: fill the target row, or append a new manual row. */
  pickFromSearch: (sku: SkuWire) => void;

  // ── Bridges ───────────────────────────────────────────────────────────────
  uiCommands: UiCommandHandlers<OrderDeskCommands>;
  /** Same dispatch by hand — the DEV console affordance (`window.__orderdesk.ui`). */
  handleUiCommand: (command: string, payload: Record<string, unknown>) => void;
  snapshot: () => OrderSnapshot;
  registerAgentSend: (fn: AgentSend) => void;

  /** Bumped on every change the agent should hear about. */
  rev: number;
}

const Ctx = createContext<OrderDeskStore | null>(null);

export function useOrderDesk(): OrderDeskStore {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useOrderDesk outside OrderDeskProvider");
  return ctx;
}

/** Debounce for the manual search bar (DESIGN §3: ~300 ms, ≥2 chars). */
const SEARCH_DEBOUNCE_MS = 300;
const SEARCH_MIN_CHARS = 2;
/** How long a highlighted row keeps pulsing. */
const HIGHLIGHT_MS = 3000;

/** A row is order-ready only when it is locked to a SKU with a real quantity. */
export function isReady(item: LineItemView): boolean {
  return item.status === "matched" && item.sku !== null && (item.quantity ?? 0) >= 1;
}

/** Defensive fill — the brain emits every field, but a row must never render half-formed. */
function toItem(v: LineItemView): LineItemView {
  const question = v.question ?? null;
  return {
    id: String(v.id),
    spoken_text: v.spoken_text ?? "",
    query: v.query ?? "",
    quantity: typeof v.quantity === "number" ? v.quantity : null,
    status: v.status ?? "resolving",
    sku: v.sku ?? null,
    family: v.family ?? null,
    variants: v.variants ?? [],
    families: v.families ?? [],
    candidates: v.candidates ?? [],
    // A question with no choices is not a question — never render an empty pill row.
    question: question && Array.isArray(question.choices) && question.choices.length > 0
      ? { text: question.text ?? "", choices: question.choices }
      : null,
    differing_axes: v.differing_axes ?? [],
    note: v.note ?? null,
    source: v.source ?? "agent",
  };
}

/** The four axes a pill label may read (DESIGN §7-bis: labels say only what differs). */
const AXES = ["variant_label", "form", "strength", "pack_size"] as const;
const AXIS_OF: Record<string, (s: SkuWire) => string> = {
  variant_label: (s) => s.variant_label ?? "",
  form: (s) => s.form ?? "",
  strength: (s) => s.strength ?? "",
  pack_size: (s) => s.pack_size ?? "",
};

/**
 * Which axes still separate a candidate set — recomputed on this side after a
 * narrowing tap, because the remainder usually differs on *fewer* axes than the
 * set the agent asked about (tap "Eye drops" on 4 QUIN and only pack size is left).
 * That is what keeps the synthesized leaf pills short.
 */
export function differingAxes(skus: SkuWire[]): string[] {
  if (skus.length < 2) return [];
  return AXES.filter((axis) => {
    const read = AXIS_OF[axis];
    const first = read(skus[0]).trim();
    return skus.some((s) => read(s).trim() !== first);
  });
}

/** `a` covers every code in `b` — how a stale, wider re-send of a question is spotted. */
function coversAll(a: SkuWire[], b: SkuWire[]): boolean {
  if (a.length < b.length) return false;
  const have = new Set(a.map((s) => s.code));
  return b.every((s) => have.has(s.code));
}

/** How many leaf pills a row may grow locally before it needs another question. */
const LOCAL_PILL_CAP = 4;

/**
 * One row's `upsert_items` merge (the pure half of {@link OrderDeskProvider}'s
 * `upsertItems`; the caller supplies the fresh `nonce`). The brain re-sends whole
 * render state, so this is a merge by id, not a patch — and three things the
 * browser owns survive it: a quantity the pharmacist typed, a choice they tapped
 * (`pinned`, overridable only by an explicit agent `matched`), and a narrowing
 * they tapped, against the agent's stale re-send of the question they just answered.
 */
export function mergeItem(cur: LineItem, view: LineItemView): LineItem {
  const keepChoice = cur.pinned && view.status !== "matched";
  // A question the pharmacist already answered by tapping, re-sent over a candidate
  // set no smaller than the one on screen, is the agent echoing the round that just
  // ended — keep the narrowing. A new question, or the same one over the remainder,
  // is the next round and lands.
  const staleQuestion =
    cur.answered !== null &&
    view.question !== null &&
    view.question.text === cur.answered &&
    coversAll(view.candidates, cur.candidates);
  const keepNarrowing = keepChoice || staleQuestion;
  return {
    ...view,
    quantity: view.quantity ?? cur.quantity,
    status: keepNarrowing ? cur.status : view.status,
    sku: keepChoice ? cur.sku : view.sku,
    family: keepChoice ? cur.family : view.family,
    variants: keepNarrowing && cur.variants.length ? cur.variants : view.variants,
    families: keepChoice && cur.families.length ? cur.families : view.families,
    candidates: keepNarrowing && cur.candidates.length ? cur.candidates : view.candidates,
    question: keepNarrowing ? cur.question : view.question,
    differing_axes: keepNarrowing ? cur.differing_axes : view.differing_axes,
    note: keepNarrowing && view.note === null ? cur.note : view.note,
    pinned: cur.pinned,
    answered: view.question !== null && !staleQuestion ? null : cur.answered,
    nonce: cur.nonce,
  };
}

/**
 * A tap on one of the question's pills, as a pure row transition (the caller
 * supplies the fresh `nonce`). DESIGN §7-bis, local-first:
 *
 *   leaf pill  → this choice IS a SKU: lock the row on it, pinned, exactly like a
 *                variant pill. No round trip, no waiting on the agent.
 *   group pill → keep only `narrows_to` of the candidates and drop the question.
 *                ≤4 left → the pills regrow here as leaves, labelled off the axes
 *                that still differ; more than that → say how many are left and let
 *                the agent's next `ask_choice` (a plain `upsert_items`) take over.
 */
export function applyChoice(it: LineItem, choice: DisambigChoice): LineItem {
  const pool = it.candidates.length ? it.candidates : it.variants;
  const keep = new Set(choice.narrows_to ?? []);
  const remaining = choice.sku_code
    ? pool.filter((s) => s.code === choice.sku_code)
    : pool.filter((s) => keep.has(s.code));
  // What the pharmacist just answered — a late re-send of it is no longer news.
  const answered = it.question?.text ?? it.answered;

  // Leaf — or a group that happens to leave exactly one SKU standing.
  if (remaining.length === 1) {
    const sku = remaining[0];
    return {
      ...it,
      status: "matched",
      sku,
      family: sku.family || it.family,
      variants: [],
      families: [],
      candidates: [],
      question: null,
      differing_axes: [],
      note: null,
      pinned: true,
      answered,
    };
  }

  // The choice named codes this screen doesn't hold — don't silently empty the
  // row; drop the question and let the agent (or the search bar) re-ask.
  if (remaining.length === 0) return { ...it, question: null, answered };

  // Few enough left to answer by pointing: grow the leaf pills right here.
  if (remaining.length <= LOCAL_PILL_CAP) {
    return {
      ...it,
      status: "multi_variant",
      variants: remaining,
      candidates: remaining,
      families: [],
      question: null,
      differing_axes: differingAxes(remaining),
      note: null,
      answered,
    };
  }

  // Still too many for pills — the row goes to "narrowed, N left" (the screen reads
  // that off `candidates`) and the agent's next question takes it from here. The
  // agent's old note goes with the question it belonged to.
  return {
    ...it,
    variants: [],
    candidates: remaining,
    question: null,
    differing_axes: differingAxes(remaining),
    note: null,
    answered,
  };
}

/**
 * Can this screen answer a family card by itself?
 *
 * The browser holds `FamilyWire` (a name, a hint, a count) and — since the brain
 * stopped floor-gating `multi_family` — the candidate SKUs behind those families.
 * But `candidates` is capped, so a big family can arrive truncated, and narrowing
 * to a *slice* of a brand would quietly hide SKUs the pharmacist asked to see.
 *
 * There is no wire field saying "you have all of this one"; the honest test is
 * arithmetic — as many of that family in `candidates` as the family claims to
 * have. Whole → the card narrows in place. Anything less → the card opens the
 * scoped search panel, and (crucially) says so on its face.
 */
export function familyHeldWhole(it: LineItemView, f: FamilyWire): boolean {
  if (f.sku_count <= 0) return false;
  return it.candidates.filter((c) => c.family === f.family).length === f.sku_count;
}

/**
 * A tap on a family card, as a pure row transition (the caller supplies the fresh
 * `nonce`) — the local-narrow twin of {@link applyChoice}, and the same three
 * outcomes:
 *
 *   1 survivor → this family has one SKU: lock the row on it, pinned, like a leaf.
 *   ≤4         → the leaf pills grow right here, labelled off the axes that still
 *                differ *within the brand* (usually far fewer than across brands).
 *   more       → "Narrowed — N left", and the agent's next question takes over.
 *
 * A row with none of that family in `candidates` is returned untouched — the
 * caller ({@link OrderDeskProvider}'s `narrowToFamily`) falls back to search
 * rather than silently emptying the row.
 */
export function applyFamily(it: LineItem, family: string): LineItem {
  const remaining = it.candidates.filter((c) => c.family === family);
  if (remaining.length === 0) return it;
  // A family card is not a question, but a row can carry both; the tap answers
  // whatever was on screen, so a late re-send of it is no longer news.
  const answered = it.question?.text ?? it.answered;

  if (remaining.length === 1) {
    const sku = remaining[0];
    return {
      ...it,
      status: "matched",
      sku,
      family: sku.family || family,
      variants: [],
      families: [],
      candidates: [],
      question: null,
      differing_axes: [],
      note: null,
      pinned: true,
      answered,
    };
  }

  // Inside one brand now, either way: the cards are spent, and the row's title
  // becomes the family the pharmacist just picked.
  const narrowed = {
    ...it,
    status: "multi_variant" as const,
    family,
    families: [],
    candidates: remaining,
    question: null,
    differing_axes: differingAxes(remaining),
    note: null,
    answered,
  };

  return remaining.length <= LOCAL_PILL_CAP
    ? { ...narrowed, variants: remaining }
    : { ...narrowed, variants: [] };
}

/**
 * The codes still in play on a row, for `state_sync`. Settled rows (matched, or
 * nothing in the catalog to point at) report `[]`; an ambiguous row reports its
 * live candidate set — the full one the agent sent, or the leaf pills on screen
 * when the set was small enough to skip the question.
 */
function ambiguousCodes(it: LineItemView): string[] {
  if (it.status === "matched" || it.status === "not_found") return [];
  const pool = it.candidates.length ? it.candidates : it.variants;
  return pool.map((s) => s.code);
}

function orderNumber(seq: number): string {
  const now = new Date();
  const hhmm = `${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}`;
  return `MS-${hhmm}-${seq}`;
}

export function OrderDeskProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("picker");
  const [scenario, setScenario] = useState<Scenario | null>(null);

  const [items, setItems] = useState<LineItem[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<HighlightState | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [orderNo, setOrderNo] = useState<string | null>(null);

  const [searchQuery, setSearchQueryState] = useState("");
  const [searchResults, setSearchResults] = useState<SkuWire[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTarget, setSearchTarget] = useState<string | null>(null);
  const [variantStrip, setVariantStrip] = useState<VariantStrip | null>(null);

  const [rev, setRev] = useState(0);

  const agentSendRef = useRef<AgentSend>(null);
  const nonceRef = useRef(0);
  const manualSeqRef = useRef(0);
  const orderSeqRef = useRef(0);
  const searchTimer = useRef<number | null>(null);
  const highlightTimer = useRef<number | null>(null);

  const pharmacy = scenario ? pharmacyById(scenario.pharmacy_id) : null;
  const bump = useCallback(() => setRev((r) => r + 1), []);

  // ── Navigation ──────────────────────────────────────────────────────────
  const startScenario = useCallback((scenarioId: string) => {
    const s = scenarioById(scenarioId);
    if (!s) return;
    setScenario(s);
    setItems([]);
    setNote(null);
    setHighlight(null);
    setConfirmed(false);
    setOrderNo(null);
    setSearchQueryState("");
    setSearchResults([]);
    setSearching(false);
    setSearchOpen(false);
    setSearchTarget(null);
    setVariantStrip(null);
    manualSeqRef.current = 0;
    setPhase("incoming");
  }, []);

  const acceptCall = useCallback(() => setPhase("call"), []);
  const declineCall = useCallback(() => setPhase("picker"), []);
  const endCall = useCallback(() => setPhase("ended"), []);
  const backToPicker = useCallback(() => {
    setScenario(null);
    setPhase("picker");
  }, []);

  const brainPayload = useCallback(
    () => (scenario ? buildBrainPayload(scenario) : {}),
    [scenario],
  );

  // ── Agent → screen ──────────────────────────────────────────────────────

  /**
   * `upsert_items` — the brain re-sends a row's whole render state, so this is a
   * merge by id, not a patch. Two things the browser owns survive the merge: a
   * quantity the pharmacist typed (an agent re-render that carries none must not
   * wipe it) and a choice the pharmacist tapped (`pinned`), which only an explicit
   * agent `matched` may override.
   */
  const upsertItems = useCallback(
    (incoming: LineItemView[]) => {
      if (!Array.isArray(incoming) || incoming.length === 0) return;
      setItems((prev) => {
        const next = [...prev];
        for (const raw of incoming) {
          const view = toItem(raw);
          const i = next.findIndex((it) => it.id === view.id);
          if (i < 0) {
            next.push({ ...view, pinned: false, answered: null, nonce: ++nonceRef.current });
            continue;
          }
          next[i] = { ...mergeItem(next[i], view), nonce: ++nonceRef.current };
        }
        return next;
      });
      bump();
    },
    [bump],
  );

  const removeIds = useCallback(
    (ids: string[]) => {
      const drop = new Set(ids ?? []);
      setItems((prev) => prev.filter((it) => !drop.has(it.id)));
      // A strip belongs to its row; the row going away takes it along.
      setVariantStrip((cur) => (cur && drop.has(cur.itemId) ? null : cur));
      bump();
    },
    [bump],
  );

  const highlightItem = useCallback(
    (id: string, itemNote: string | null) => {
      setHighlight({ id, note: itemNote ?? null, nonce: ++nonceRef.current });
      // The note also sticks to the row, so it survives the pulse.
      if (itemNote) {
        setItems((prev) => prev.map((it) => (it.id === id ? { ...it, note: itemNote } : it)));
      }
      if (highlightTimer.current) window.clearTimeout(highlightTimer.current);
      highlightTimer.current = window.setTimeout(() => setHighlight(null), HIGHLIGHT_MS);
      bump();
    },
    [bump],
  );

  const showSearchResults = useCallback((query: string, results: SkuWire[]) => {
    setSearching(false);
    setSearchResults(Array.isArray(results) ? results : []);
    setSearchOpen(true);
    // Late answer to a query the pharmacist has already retyped past: keep the
    // rows (they are still the best the brain has) but do not rewrite the field.
    void query;
  }, []);

  /**
   * `show_variants` — the answer to one row's `list_variants`. It fills the strip
   * that is already open and nothing else: a late answer to a strip the pharmacist
   * has since dismissed (or reopened on another row) is dropped, never reopens.
   * No `bump()` — this changed the display, not the cart.
   */
  const showVariants = useCallback(
    (itemId: string, family: string, results: SkuWire[], axes: string[]) => {
      setVariantStrip((cur) =>
        cur && cur.itemId === itemId
          ? {
              ...cur,
              family: family || cur.family,
              results: Array.isArray(results) ? results : [],
              differingAxes: Array.isArray(axes) ? axes : [],
              loading: false,
            }
          : cur,
      );
    },
    [],
  );

  const showNote = useCallback(
    (text: string) => {
      setNote(text || null);
      bump();
    },
    [bump],
  );

  const dismissNote = useCallback(() => setNote(null), []);

  // The brain's six commands, one handler each. The map is checked against
  // `OrderDeskCommands` — a name brain.py doesn't declare is a compile error here,
  // and each `args` is the shape its Python `Action` emits, so there is nothing
  // left to coerce or null-check.
  const uiCommands: UiCommandHandlers<OrderDeskCommands> = useMemo(
    () => ({
      upsert_items: ({ items: incoming }) => upsertItems(incoming),
      remove_items: ({ ids }) => removeIds(ids),
      highlight_item: ({ id, note: n }) => highlightItem(id, n),
      show_search_results: ({ query, results }) => showSearchResults(query, results),
      show_variants: ({ item_id, family, results, differing_axes }) =>
        showVariants(item_id, family, results, differing_axes),
      order_note: ({ text }) => showNote(text),
    }),
    [upsertItems, removeIds, highlightItem, showSearchResults, showVariants, showNote],
  );

  // Same dispatch, by hand — for `window.__orderdesk.ui('upsert_items', {items:[…]})`.
  const handleUiCommand = useCallback(
    (command: string, payload: Record<string, unknown>) => {
      const map = uiCommands as unknown as Record<string, ((args: unknown) => void) | undefined>;
      map[command]?.(payload);
    },
    [uiCommands],
  );

  // ── Screen → agent ──────────────────────────────────────────────────────

  const choosePill = useCallback(
    (itemId: string, sku: SkuWire) => {
      setItems((prev) =>
        prev.map((it) =>
          it.id === itemId
            ? {
                ...it,
                status: "matched",
                sku,
                family: sku.family || it.family,
                families: [],
                candidates: [],
                question: null,
                note: null,
                pinned: true,
                nonce: ++nonceRef.current,
              }
            : it,
        ),
      );
      bump();
    },
    [bump],
  );

  /**
   * A tap on a question pill ({@link applyChoice}). `rev` bumps either way, so
   * `state_sync` carries the surviving `candidate_codes` — that is how the agent
   * *sees* the tap and knows what to ask next.
   */
  const chooseChoice = useCallback(
    (itemId: string, choice: DisambigChoice) => {
      setItems((prev) =>
        prev.map((it) =>
          it.id === itemId ? { ...applyChoice(it, choice), nonce: ++nonceRef.current } : it,
        ),
      );
      bump();
    },
    [bump],
  );

  const runCatalogSearch = useCallback((query: string) => {
    const send = agentSendRef.current;
    if (!send || query.trim().length < SEARCH_MIN_CHARS) return;
    setSearching(true);
    send(CLIENT_MESSAGE.catalogSearch, { query: query.trim() });
  }, []);

  const setSearchQuery = useCallback(
    (query: string) => {
      setSearchQueryState(query);
      setSearchOpen(query.trim().length > 0);
      if (searchTimer.current) window.clearTimeout(searchTimer.current);
      if (query.trim().length < SEARCH_MIN_CHARS) {
        setSearchResults([]);
        setSearching(false);
        return;
      }
      searchTimer.current = window.setTimeout(() => runCatalogSearch(query), SEARCH_DEBOUNCE_MS);
    },
    [runCatalogSearch],
  );

  const closeSearch = useCallback(() => {
    if (searchTimer.current) window.clearTimeout(searchTimer.current);
    setSearchOpen(false);
    setSearchQueryState("");
    setSearchResults([]);
    setSearching(false);
    setSearchTarget(null);
  }, []);

  /**
   * Scope the search panel to a family, for this row; picking a result is what
   * locks the SKU. This is the *fallback* path now — a family whose SKUs this
   * screen only holds a slice of (and the "+N more" overflow pills, which are an
   * explicit hand-off to the panel by construction).
   */
  const chooseFamily = useCallback(
    (itemId: string, family: string) => {
      setSearchTarget(itemId);
      setSearchQueryState(family);
      setSearchOpen(true);
      if (searchTimer.current) window.clearTimeout(searchTimer.current);
      runCatalogSearch(family);
    },
    [runCatalogSearch],
  );

  /**
   * A family card the browser holds whole: narrow the row's candidates to that
   * family on this screen ({@link applyFamily}), the way a group choice pill
   * already narrows. `rev` bumps, so `state_sync` carries the surviving
   * `candidate_codes` — that is how the agent *sees* the tap and knows what to
   * ask next. If the row turns out to hold nothing of that family after all,
   * this degrades to the scoped search rather than emptying the row.
   */
  const narrowToFamily = useCallback(
    (itemId: string, family: string) => {
      const row = items.find((it) => it.id === itemId);
      if (!row || row.candidates.every((c) => c.family !== family)) {
        chooseFamily(itemId, family);
        return;
      }
      setItems((prev) =>
        prev.map((it) =>
          it.id === itemId ? { ...applyFamily(it, family), nonce: ++nonceRef.current } : it,
        ),
      );
      bump();
    },
    [bump, chooseFamily, items],
  );

  // ── Inline variant edit ─────────────────────────────────────────────────

  /**
   * "Change variant" on a matched row. The family is already established and
   * stays established — this asks only for its siblings, so the pharmacist can
   * fix the variant without deleting and re-dictating the line. Silent, like
   * `catalog_search`: with no live call there is nobody to ask, so it no-ops.
   */
  const openVariants = useCallback((itemId: string, family: string) => {
    const send = agentSendRef.current;
    if (!send || !family) return;
    setVariantStrip({ itemId, family, results: [], differingAxes: [], loading: true });
    send(CLIENT_MESSAGE.listVariants, { item_id: itemId, family });
  }, []);

  const closeVariants = useCallback(() => setVariantStrip(null), []);

  /**
   * Tap a sibling: the row re-locks on the new SKU with the quantity already
   * ordered intact — the whole point of the strip — and `pinned`, so a late agent
   * echo of the old SKU cannot undo it. `rev` bumps; `state_sync` then carries the
   * new `sku_code`, which is what keeps the brain's mirror off a stale family.
   */
  const pickVariant = useCallback(
    (itemId: string, sku: SkuWire) => {
      setItems((prev) =>
        prev.map((it) =>
          it.id === itemId
            ? {
                ...it,
                status: "matched",
                sku,
                family: sku.family || it.family,
                variants: [],
                families: [],
                candidates: [],
                question: null,
                differing_axes: [],
                note: null,
                quantity: it.quantity ?? 1,
                pinned: true,
                nonce: ++nonceRef.current,
              }
            : it,
        ),
      );
      setVariantStrip(null);
      bump();
    },
    [bump],
  );

  const pickFromSearch = useCallback(
    (sku: SkuWire) => {
      const target = searchTarget;
      if (target) {
        setItems((prev) =>
          prev.map((it) =>
            it.id === target
              ? {
                  ...it,
                  status: "matched",
                  sku,
                  family: sku.family || it.family,
                  variants: [],
                  families: [],
                  candidates: [],
                  question: null,
                  differing_axes: [],
                  note: null,
                  quantity: it.quantity ?? 1,
                  pinned: true,
                  nonce: ++nonceRef.current,
                }
              : it,
          ),
        );
      } else {
        const id = `m${++manualSeqRef.current}`;
        setItems((prev) => [
          ...prev,
          {
            id,
            spoken_text: sku.name,
            query: searchQuery.trim(),
            quantity: 1,
            status: "matched",
            sku,
            family: sku.family,
            variants: [],
            families: [],
            candidates: [],
            question: null,
            differing_axes: [],
            note: null,
            source: "manual",
            pinned: true,
            answered: null,
            nonce: ++nonceRef.current,
          },
        ]);
      }
      closeSearch();
      bump();
    },
    [bump, closeSearch, searchQuery, searchTarget],
  );

  const setQuantity = useCallback(
    (itemId: string, quantity: number) => {
      const q = Math.max(1, Math.min(999, Math.round(quantity)));
      setItems((prev) => prev.map((it) => (it.id === itemId ? { ...it, quantity: q } : it)));
      bump();
    },
    [bump],
  );

  const removeItem = useCallback(
    (itemId: string) => {
      setItems((prev) => prev.filter((it) => it.id !== itemId));
      setVariantStrip((cur) => (cur && cur.itemId === itemId ? null : cur));
      bump();
    },
    [bump],
  );

  const blockedIds = useMemo(() => items.filter((it) => !isReady(it)).map((it) => it.id), [items]);
  const canConfirm = items.length > 0 && blockedIds.length === 0 && !confirmed;
  const totalPtr = useMemo(
    () => items.reduce((sum, it) => sum + (it.sku ? it.sku.ptr * (it.quantity ?? 0) : 0), 0),
    [items],
  );

  const confirmOrder = useCallback(() => {
    if (items.length === 0 || blockedIds.length > 0 || confirmed) return;
    setConfirmed(true);
    setOrderNo(orderNumber(++orderSeqRef.current));
    bump(); // state_sync carries `screen: "confirmed"` — the agent closes on it
  }, [blockedIds.length, bump, confirmed, items.length]);

  /**
   * The authoritative cart, exactly as `OrderSnapshot` (types.ts / DESIGN §3).
   * `total_mrp` is the MRP-denominated order value the field name promises; the
   * cart bar on screen shows the PTR total instead (`totalPtr`), because that is
   * the number the pharmacist is actually buying at.
   *
   * `candidate_codes` is the sharpest-question feedback channel: while a row is
   * still ambiguous it carries the codes still standing, so a pill tap the agent
   * never heard shows up on its next grounding as a *smaller* set — that is how
   * it knows to ask the next question, or that the row already answered itself.
   */
  const snapshot = useCallback((): OrderSnapshot => {
    const total = items.reduce(
      (sum, it) => sum + (it.sku ? it.sku.mrp * (it.quantity ?? 0) : 0),
      0,
    );
    return {
      screen: confirmed ? "confirmed" : "order",
      items: items.map((it) => ({
        id: it.id,
        spoken_text: it.spoken_text,
        status: it.status,
        sku_code: it.sku?.code ?? null,
        sku_name: it.sku?.name ?? null,
        pack_size: it.sku?.pack_size ?? null,
        quantity: it.quantity,
        source: it.source,
        candidate_codes: ambiguousCodes(it),
      })),
      total_mrp: Math.round(total * 100) / 100,
      item_count: items.length,
      confirmed,
    };
  }, [confirmed, items]);

  const registerAgentSend = useCallback((fn: AgentSend) => {
    agentSendRef.current = fn;
  }, []);

  const value = useMemo<OrderDeskStore>(
    () => ({
      phase,
      scenario,
      pharmacy,
      brainPayload,
      startScenario,
      acceptCall,
      declineCall,
      endCall,
      backToPicker,
      items,
      note,
      dismissNote,
      highlight,
      confirmed,
      orderNo,
      blockedIds,
      canConfirm,
      totalPtr,
      choosePill,
      chooseChoice,
      narrowToFamily,
      chooseFamily,
      setQuantity,
      removeItem,
      confirmOrder,
      variantStrip,
      openVariants,
      closeVariants,
      pickVariant,
      searchQuery,
      searchResults,
      searching,
      searchOpen,
      searchTarget,
      setSearchQuery,
      closeSearch,
      pickFromSearch,
      uiCommands,
      handleUiCommand,
      snapshot,
      registerAgentSend,
      rev,
    }),
    [
      phase, scenario, pharmacy, brainPayload, startScenario, acceptCall, declineCall, endCall,
      backToPicker, items, note, dismissNote, highlight, confirmed, orderNo, blockedIds,
      canConfirm, totalPtr, choosePill, chooseChoice, narrowToFamily, chooseFamily, setQuantity,
      removeItem, confirmOrder,
      variantStrip, openVariants, closeVariants, pickVariant,
      searchQuery, searchResults, searching, searchOpen, searchTarget, setSearchQuery,
      closeSearch, pickFromSearch, uiCommands, handleUiCommand, snapshot, registerAgentSend, rev,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
