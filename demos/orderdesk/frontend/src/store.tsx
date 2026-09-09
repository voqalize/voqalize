/**
 * Shared state for the OrderDesk demo — the pharmacist's phone and the voice call
 * drive one store, so the agent and the pharmacist edit the same cart.
 *
 * Two bridges, both fine-grained and typed (CLAUDE.md), and neither carrying a cart:
 *   - the brain's `ui_command`s land on {@link OrderDeskStore.handleUiCommand},
 *     which narrows on `command` against `actions.gen.ts` — generated from
 *     brain.py's `Action` classes, so a payload needs no coercion and the `default`
 *     arm is an exhaustiveness check. Each one names one row and carries only what
 *     moved on it: `row_opened`, then `row_matched` / `row_variants` /
 *     `row_families` / `row_not_found`, with `row_question` and `row_quantity`
 *     between. That is why this store has no merge and no pin — a `row_question`
 *     that arrives after the pharmacist already settled the row puts a question
 *     back and nothing else, because it carries no SKU to un-settle it with;
 *   - every gesture the pharmacist makes goes out *named*, as a typed
 *     {@link DeskEvent} — `quantity_set`, `sku_chosen`, `row_removed` — the instant
 *     he makes it. There is no snapshot behind them: an act this screen does not
 *     send is an act the brain never learns about, so the event set has to be
 *     complete, and a gap shows up as a gap rather than being quietly reconciled.
 *
 * The cart is keyed by line-item id: the brain numbers its own rows (`li1`…); rows
 * the pharmacist adds from the search bar are numbered `m1`… on this side.
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
import { CLIENT_MESSAGE, sendDeskEvent, type AgentSend, type DeskEvent } from "./clientMessages";
import {
  asUiAction,
  unhandledUiAction,
  type RowFamilies,
  type RowMatched,
  type RowOpened,
  type RowQuantity,
  type RowQuestion,
  type RowVariants,
} from "./actions.gen";
import type {
  DisambigChoice,
  DisambigQuestion,
  FamilyWire,
  LineItem,
  Pharmacy,
  Phase,
  Scenario,
  SkuWire,
} from "./types";

export type { LineItem };

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

  // ── Manual edits (each goes out as its own typed DeskEvent) ───────────────
  /** Tap a variant pill: promote the row to `matched` on the SkuWire it already holds. */
  choosePill: (itemId: string, sku: SkuWire) => void;
  /**
   * Tap a pill on the agent's disambiguation question (DESIGN §7-bis). Local-first:
   * a leaf answers the row outright, a group narrows the candidate set on this
   * screen and — when few enough remain — grows the leaf pills here, without a
   * round trip. Either way a `question_answered` goes out naming what survived, so
   * the agent asks about what is left rather than repeating itself.
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
  /** Replay one `ui-command` onto the screen; also the DEV console's `window.__orderdesk.ui`. */
  handleUiCommand: (command: string, payload: unknown) => void;
  registerAgentSend: (fn: AgentSend) => void;
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
export function isReady(item: LineItem): boolean {
  return item.status === "matched" && item.sku !== null && (item.quantity ?? 0) >= 1;
}

/** A question with no choices is not a question — never render an empty pill row. */
function asQuestion(q: DisambigQuestion | null): DisambigQuestion | null {
  return q && Array.isArray(q.choices) && q.choices.length > 0 ? q : null;
}

/** Everything an ambiguity leaves behind, cleared in one place. */
const SETTLED = {
  variants: [] as SkuWire[],
  families: [] as FamilyWire[],
  candidates: [] as SkuWire[],
  question: null,
  differing_axes: [] as string[],
  note: null,
} as const;

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

/** How many leaf pills a row may grow locally before it needs another question. */
const LOCAL_PILL_CAP = 4;

/**
 * A tap on one of the question's pills, as a pure row transition. DESIGN §7-bis,
 * local-first:
 *
 *   leaf pill  → this choice IS a SKU: lock the row on it, exactly like a variant
 *                pill. No round trip, no waiting on the agent.
 *   group pill → keep only `narrows_to` of the candidates and drop the question.
 *                ≤4 left → the pills regrow here as leaves, labelled off the axes
 *                that still differ; more than that → say how many are left and let
 *                the agent's next `row_question` take over.
 */
export function applyChoice(it: LineItem, choice: DisambigChoice): LineItem {
  const pool = it.candidates.length ? it.candidates : it.variants;
  const keep = new Set(choice.narrows_to ?? []);
  const remaining = choice.sku_code
    ? pool.filter((s) => s.code === choice.sku_code)
    : pool.filter((s) => keep.has(s.code));

  // Leaf — or a group that happens to leave exactly one SKU standing.
  if (remaining.length === 1) {
    const sku = remaining[0];
    return { ...it, ...SETTLED, status: "matched", sku, family: sku.family || it.family };
  }

  // The choice named codes this screen doesn't hold — don't silently empty the
  // row; drop the question and let the agent (or the search bar) re-ask.
  if (remaining.length === 0) return { ...it, question: null };

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
export function familyHeldWhole(it: LineItem, f: FamilyWire): boolean {
  if (f.sku_count <= 0) return false;
  return it.candidates.filter((c) => c.family === f.family).length === f.sku_count;
}

/**
 * A tap on a family card, as a pure row transition — the local-narrow twin of
 * {@link applyChoice}, and the same three outcomes:
 *
 *   1 survivor → this family has one SKU: lock the row on it, like a leaf.
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

  if (remaining.length === 1) {
    const sku = remaining[0];
    return { ...it, ...SETTLED, status: "matched", sku, family: sku.family || family };
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
  };

  return remaining.length <= LOCAL_PILL_CAP
    ? { ...narrowed, variants: remaining }
    : { ...narrowed, variants: [] };
}

/**
 * The codes still in play on a row — what a narrowing tap reports as having
 * survived it. Settled rows (matched, or nothing in the catalog to point at)
 * report `[]`; an ambiguous row reports its live candidate set, the full one the
 * agent sent or the leaf pills on screen when the set was small enough to skip
 * the question.
 */
function ambiguousCodes(it: LineItem): string[] {
  if (it.status === "matched" || it.status === "not_found") return [];
  const pool = it.candidates.length ? it.candidates : it.variants;
  return pool.map((s) => s.code);
}

/**
 * What a local narrowing tap *was*, told apart by where it left the row.
 *
 * `applyChoice` and `applyFamily` both have three outcomes, and only two of them
 * are a narrowing: a tap that leaves exactly one SKU standing has settled the row,
 * and reporting that as "narrowed to 1" would be describing the arithmetic instead
 * of the act. So a settling tap is a `sku_chosen` like any other pill, and only a
 * tap that genuinely left a choice open reports what survived it.
 */
export function tapEvent(
  before: LineItem,
  after: LineItem,
  narrowed: (survivingCodes: string[]) => DeskEvent,
): DeskEvent {
  if (after.status === "matched" && after.sku && after.sku.code !== before.sku?.code) {
    return {
      t: "sku_chosen",
      d: { item_id: after.id, sku_code: after.sku.code, sku_name: after.sku.name, via: "pill" },
    };
  }
  return narrowed(ambiguousCodes(after));
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

  const agentSendRef = useRef<AgentSend>(null);
  const nonceRef = useRef(0);
  const manualSeqRef = useRef(0);
  const orderSeqRef = useRef(0);
  const searchTimer = useRef<number | null>(null);
  const highlightTimer = useRef<number | null>(null);

  const pharmacy = scenario ? pharmacyById(scenario.pharmacy_id) : null;

  /**
   * Tell the brain what he just did, the instant he does it. This is the only
   * channel — nothing else carries his edits — so it is silent only when there is
   * genuinely nobody to tell: before the call is live the brain has not been born
   * yet, and it starts from an empty order when it is.
   */
  const emit = useCallback((event: DeskEvent) => sendDeskEvent(agentSendRef.current, event), []);

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
   * Move one row, by id. Every `row_*` command routes through here, which is why
   * none of them can touch a row they do not name and none of them can undo a part
   * of the row they say nothing about. A command for a row this screen does not
   * hold is dropped — `row_opened` is the only one that may create one.
   */
  const patchRow = useCallback((id: string, patch: (it: LineItem) => LineItem) => {
    setItems((prev) => prev.map((it) => (it.id === id ? patch(it) : it)));
  }, []);

  /** `row_opened` — a row he just named, greyed, before the catalog work lands. */
  const rowOpened = useCallback((row: RowOpened) => {
    setItems((prev) =>
      prev.some((it) => it.id === row.id)
        ? prev
        : [
            ...prev,
            {
              ...SETTLED,
              id: row.id,
              spoken_text: row.spoken_text,
              query: row.query,
              quantity: row.quantity,
              status: "resolving",
              sku: null,
              family: null,
              source: "agent",
            },
          ],
    );
  }, []);

  /** `row_resolving` — a re-resolve started; the row goes back to grey and empty. */
  const rowResolving = useCallback(
    (id: string) => patchRow(id, (it) => ({ ...it, ...SETTLED, status: "resolving", sku: null })),
    [patchRow],
  );

  const rowMatched = useCallback(
    (row: RowMatched) =>
      patchRow(row.id, (it) => ({
        ...it,
        ...SETTLED,
        status: "matched",
        sku: row.sku,
        family: row.sku.family || row.family || it.family,
      })),
    [patchRow],
  );

  const rowFamilies = useCallback(
    (row: RowFamilies) =>
      patchRow(row.id, (it) => ({
        ...it,
        ...SETTLED,
        status: "multi_family",
        sku: null,
        families: row.families,
        candidates: row.candidates,
        differing_axes: row.differing_axes,
      })),
    [patchRow],
  );

  const rowVariants = useCallback(
    (row: RowVariants) =>
      patchRow(row.id, (it) => ({
        ...it,
        ...SETTLED,
        status: "multi_variant",
        sku: null,
        family: row.family,
        variants: row.variants,
        candidates: row.candidates,
        differing_axes: row.differing_axes,
      })),
    [patchRow],
  );

  const rowNotFound = useCallback(
    (id: string) => patchRow(id, (it) => ({ ...it, ...SETTLED, status: "not_found", sku: null })),
    [patchRow],
  );

  /**
   * `row_question` — the agent's one splitting question, and *only* that. This is
   * where the old whole-row push hurt most: a question re-sent after the pharmacist
   * had already tapped past it used to reset the row's SKU and status with it, so a
   * settled row flickered back open and the browser grew a pin to stop it. A late
   * one now puts a question on a matched row at worst, which the row itself declines
   * to render (`pages.tsx`: a matched row has nothing left to ask about).
   */
  const rowQuestion = useCallback(
    (row: RowQuestion) =>
      patchRow(row.id, (it) => ({ ...it, question: asQuestion(row.question), note: null })),
    [patchRow],
  );

  /** `row_quantity` — how many, and nothing else. The one row action that keeps the note. */
  const rowQuantity = useCallback(
    (row: RowQuantity) => patchRow(row.id, (it) => ({ ...it, quantity: row.quantity })),
    [patchRow],
  );

  const removeIds = useCallback((ids: string[]) => {
    const drop = new Set(ids ?? []);
    setItems((prev) => prev.filter((it) => !drop.has(it.id)));
    // A strip belongs to its row; the row going away takes it along.
    setVariantStrip((cur) => (cur && drop.has(cur.itemId) ? null : cur));
  }, []);

  const highlightItem = useCallback(
    (id: string, itemNote: string | null) => {
      setHighlight({ id, note: itemNote ?? null, nonce: ++nonceRef.current });
      // The note also sticks to the row, so it survives the pulse.
      if (itemNote) patchRow(id, (it) => ({ ...it, note: itemNote }));
      if (highlightTimer.current) window.clearTimeout(highlightTimer.current);
      highlightTimer.current = window.setTimeout(() => setHighlight(null), HIGHLIGHT_MS);
    },
    [patchRow],
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

  const showNote = useCallback((text: string) => setNote(text || null), []);

  const dismissNote = useCallback(() => setNote(null), []);

  // The brain's commands. Each payload is the shape its Python `Action` emits, so
  // there is nothing left to coerce or null-check, and adding one more `Action`
  // fails to compile here until it is handled.
  const handleUiCommand = useCallback(
    (command: string, payload: unknown) => {
      const action = asUiAction(command, payload);
      if (!action) return;
      switch (action.command) {
        case "row_opened":
          rowOpened(action.payload);
          break;
        case "row_resolving":
          rowResolving(action.payload.id);
          break;
        case "row_matched":
          rowMatched(action.payload);
          break;
        case "row_families":
          rowFamilies(action.payload);
          break;
        case "row_variants":
          rowVariants(action.payload);
          break;
        case "row_not_found":
          rowNotFound(action.payload.id);
          break;
        case "row_question":
          rowQuestion(action.payload);
          break;
        case "row_quantity":
          rowQuantity(action.payload);
          break;
        case "remove_items":
          removeIds(action.payload.ids);
          break;
        case "highlight_item":
          highlightItem(action.payload.id, action.payload.note);
          break;
        case "show_search_results":
          showSearchResults(action.payload.query, action.payload.results);
          break;
        case "show_variants": {
          const { item_id, family, results, differing_axes } = action.payload;
          showVariants(item_id, family, results, differing_axes);
          break;
        }
        case "order_note":
          showNote(action.payload.text);
          break;
        default:
          unhandledUiAction(action);
      }
    },
    [
      rowOpened,
      rowResolving,
      rowMatched,
      rowFamilies,
      rowVariants,
      rowNotFound,
      rowQuestion,
      rowQuantity,
      removeIds,
      highlightItem,
      showSearchResults,
      showVariants,
      showNote,
    ],
  );

  // ── Screen → agent ──────────────────────────────────────────────────────

  const choosePill = useCallback(
    (itemId: string, sku: SkuWire) => {
      emit({
        t: "sku_chosen",
        d: { item_id: itemId, sku_code: sku.code, sku_name: sku.name, via: "pill" },
      });
      patchRow(itemId, (it) => ({
        ...it,
        ...SETTLED,
        status: "matched",
        sku,
        family: sku.family || it.family,
      }));
    },
    [emit, patchRow],
  );

  /**
   * A tap on a question pill ({@link applyChoice}). Local-first, so the row moves
   * before the agent knows — and {@link tapEvent} is what tells it *what he did*
   * rather than leaving it to spot a smaller candidate set in the next snapshot.
   */
  const chooseChoice = useCallback(
    (itemId: string, choice: DisambigChoice) => {
      const cur = items.find((it) => it.id === itemId);
      if (cur) {
        emit(
          tapEvent(cur, applyChoice(cur, choice), (surviving_codes) => ({
            t: "question_answered",
            d: {
              item_id: itemId,
              question: cur.question?.text ?? "",
              answer: choice.label,
              surviving_codes,
            },
          })),
        );
      }
      patchRow(itemId, (it) => applyChoice(it, choice));
    },
    [emit, items, patchRow],
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
   * already narrows. A `family_chosen` goes out naming what survived — that is how
   * the agent sees the tap and knows what to ask next. If the row turns out to hold
   * nothing of that family after all, this degrades to the scoped search rather
   * than emptying the row.
   */
  const narrowToFamily = useCallback(
    (itemId: string, family: string) => {
      const row = items.find((it) => it.id === itemId);
      if (!row || row.candidates.every((c) => c.family !== family)) {
        chooseFamily(itemId, family);
        return;
      }
      emit(
        tapEvent(row, applyFamily(row, family), (surviving_codes) => ({
          t: "family_chosen",
          d: { item_id: itemId, family, surviving_codes },
        })),
      );
      patchRow(itemId, (it) => applyFamily(it, family));
    },
    [chooseFamily, emit, items, patchRow],
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
   * ordered intact — the whole point of the strip. A `sku_chosen` (`via: "variant"`)
   * goes out, which is what keeps the brain's mirror off a stale family.
   */
  const pickVariant = useCallback(
    (itemId: string, sku: SkuWire) => {
      emit({
        t: "sku_chosen",
        d: { item_id: itemId, sku_code: sku.code, sku_name: sku.name, via: "variant" },
      });
      patchRow(itemId, (it) => ({
        ...it,
        ...SETTLED,
        status: "matched",
        sku,
        family: sku.family || it.family,
        quantity: it.quantity ?? 1,
      }));
      setVariantStrip(null);
    },
    [emit, patchRow],
  );

  const pickFromSearch = useCallback(
    (sku: SkuWire) => {
      const target = searchTarget;
      if (target) {
        emit({
          t: "sku_chosen",
          d: { item_id: target, sku_code: sku.code, sku_name: sku.name, via: "search" },
        });
        patchRow(target, (it) => ({
          ...it,
          ...SETTLED,
          status: "matched",
          sku,
          family: sku.family || it.family,
          quantity: it.quantity ?? 1,
        }));
      } else {
        const id = `m${++manualSeqRef.current}`;
        emit({
          t: "row_added",
          d: {
            item_id: id,
            sku_code: sku.code,
            sku_name: sku.name,
            query: searchQuery.trim(),
            quantity: 1,
          },
        });
        setItems((prev) => [
          ...prev,
          {
            ...SETTLED,
            id,
            spoken_text: sku.name,
            query: searchQuery.trim(),
            quantity: 1,
            status: "matched",
            sku,
            family: sku.family,
            source: "manual",
          },
        ]);
      }
      closeSearch();
    },
    [closeSearch, emit, patchRow, searchQuery, searchTarget],
  );

  const setQuantity = useCallback(
    (itemId: string, quantity: number) => {
      const q = Math.max(1, Math.min(999, Math.round(quantity)));
      emit({ t: "quantity_set", d: { item_id: itemId, quantity: q } });
      patchRow(itemId, (it) => ({ ...it, quantity: q }));
    },
    [emit, patchRow],
  );

  const removeItem = useCallback(
    (itemId: string) => {
      const gone = items.find((it) => it.id === itemId);
      emit({
        t: "row_removed",
        d: { item_id: itemId, spoken_text: gone?.spoken_text ?? "" },
      });
      setItems((prev) => prev.filter((it) => it.id !== itemId));
      setVariantStrip((cur) => (cur && cur.itemId === itemId ? null : cur));
    },
    [emit, items],
  );

  const blockedIds = useMemo(() => items.filter((it) => !isReady(it)).map((it) => it.id), [items]);
  const canConfirm = items.length > 0 && blockedIds.length === 0 && !confirmed;
  const totalPtr = useMemo(
    () => items.reduce((sum, it) => sum + (it.sku ? it.sku.ptr * (it.quantity ?? 0) : 0), 0),
    [items],
  );

  const confirmOrder = useCallback(() => {
    if (items.length === 0 || blockedIds.length > 0 || confirmed) return;
    const orderNumberNow = orderNumber(++orderSeqRef.current);
    setConfirmed(true);
    setOrderNo(orderNumberNow);
    emit({
      t: "order_confirmed",
      d: {
        order_no: orderNumberNow,
        item_count: items.length,
        total_mrp: items.reduce((sum, it) => sum + (it.sku ? it.sku.mrp * (it.quantity ?? 0) : 0), 0),
      },
    });
  }, [blockedIds.length, confirmed, emit, items]);

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
      handleUiCommand,
      registerAgentSend,
    }),
    [
      phase, scenario, pharmacy, brainPayload, startScenario, acceptCall, declineCall, endCall,
      backToPicker, items, note, dismissNote, highlight, confirmed, orderNo, blockedIds,
      canConfirm, totalPtr, choosePill, chooseChoice, narrowToFamily, chooseFamily, setQuantity,
      removeItem, confirmOrder,
      variantStrip, openVariants, closeVariants, pickVariant,
      searchQuery, searchResults, searching, searchOpen, searchTarget, setSearchQuery,
      closeSearch, pickFromSearch, handleUiCommand, registerAgentSend,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
