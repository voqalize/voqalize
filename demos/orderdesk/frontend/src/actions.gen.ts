// Generated from demos/orderdesk/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types demos/orderdesk/backend/brain.py -o demos/orderdesk/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

/** A row he just named — greyed and shimmering, before the catalog work runs. */
export interface RowOpened {
  id: string;

  spoken_text: string;

  query: string;

  quantity: number | null;
}

/** The row went back to grey — a re-resolve started on it. */
export interface RowResolving {
  id: string;
}

/** The row settled on one SKU. Everything the ambiguity left behind is spent. */
export interface RowMatched {
  id: string;

  sku: SkuWire;

  family: string;
}

/** Two to five brands could match — the option cards. */
export interface RowFamilies {
  id: string;

  families: FamilyWire[];

  candidates: SkuWire[];

  differing_axes: string[];
}

/**
 * One brand, several SKUs — leaf pills under `_QUESTION_FLOOR`, a
 * candidate set above it (DESIGN §7-bis).
 */
export interface RowVariants {
  id: string;

  family: string | null;

  variants: SkuWire[];

  candidates: SkuWire[];

  differing_axes: string[];
}

/** Nothing in the catalog answers to what he said. */
export interface RowNotFound {
  id: string;
}

/** One splitting question on a row, rendered as pills instead of its candidates. */
export interface RowQuestion {
  id: string;

  question: DisambigQuestion;
}

/** How many of one row he wants. The only row action that leaves a note standing. */
export interface RowQuantity {
  id: string;

  quantity: number | null;
}

/** The agent dropped rows from the order. */
export interface RemoveItems {
  ids: string[];
}

/** Scroll to and pulse one row — the agent is asking about it. */
export interface HighlightItem {
  id: string;

  note: string | null;
}

/** The floor-free answer to the manual search bar's `catalog_search`. */
export interface ShowSearchResults {
  query: string;

  results: SkuWire[];
}

/**
 * The floor-free answer to a row's `list_variants` — the siblings of one
 * matched SKU, for the inline "Change variant" strip.
 *
 * Deliberately not one of the `Row*` actions: the row is unchanged until he
 * picks one, so this carries the family's SKUs beside the row rather than through
 * it. The
 * family is usually right and only the variant wrong, and deleting a row to re-add
 * it is the painful path this exists to remove. `differing_axes` is what the
 * strip labels its pills by, so a family that differs only on pack size reads
 * "75 GM / 100 GM" and not the whole product name three times over.
 */
export interface ShowVariants {
  item_id: string;

  family: string;

  results: SkuWire[];

  differing_axes: string[];
}

/** One-line banner above the list — a scheme or stock callout. */
export interface OrderNote {
  text: string;
}

// ── Shapes used by the actions above ───────────────────────────────

/**
 * One pill of a sharpest question — a leaf SKU or a group of them.
 *
 * `sku_code` is set only when this choice *is* a single SKU: the browser can then
 * promote the row to `matched` on the tap, without asking anyone. Otherwise the tap
 * narrows the row's `candidates` to `narrows_to` and the next question is asked
 * over the remainder (DESIGN §7-bis).
 */
export interface DisambigChoice {
  label: string;

  sku_code: string | null;

  narrows_to: string[];
}

/**
 * The question the model asked, as the screen renders it — 2-4 choices whose
 * union covers every current candidate. Rendered *instead of* variants/families.
 */
export interface DisambigQuestion {
  text: string;

  choices: DisambigChoice[];
}

/** One candidate brand family — the option card shown when 2-5 brands could match. */
export interface FamilyWire {
  family: string;

  manufacturers: string[];

  forms: string[];

  sku_count: number;

  hint: string;
}

/**
 * One catalog SKU as the browser renders it — `SkuView.wire()` from
 * `search.py` (DESIGN §2), validated into a shape this file owns.
 */
export interface SkuWire {
  code: string;

  name: string;

  family: string;

  variant_label: string;

  form: string;

  strength: string;

  pack_size: string;

  mrp: number;

  ptr: number;

  stock: number;

  manufacturer: string;

  scheme: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'row_opened'; payload: RowOpened }
  | { command: 'row_resolving'; payload: RowResolving }
  | { command: 'row_matched'; payload: RowMatched }
  | { command: 'row_families'; payload: RowFamilies }
  | { command: 'row_variants'; payload: RowVariants }
  | { command: 'row_not_found'; payload: RowNotFound }
  | { command: 'row_question'; payload: RowQuestion }
  | { command: 'row_quantity'; payload: RowQuantity }
  | { command: 'remove_items'; payload: RemoveItems }
  | { command: 'highlight_item'; payload: HighlightItem }
  | { command: 'show_search_results'; payload: ShowSearchResults }
  | { command: 'show_variants'; payload: ShowVariants }
  | { command: 'order_note'; payload: OrderNote };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'row_opened',
  'row_resolving',
  'row_matched',
  'row_families',
  'row_variants',
  'row_not_found',
  'row_question',
  'row_quantity',
  'remove_items',
  'highlight_item',
  'show_search_results',
  'show_variants',
  'order_note',
];

const _known = new Set<string>(UI_ACTION_COMMANDS);

/**
 * Narrow a `ui-command` off the wire. Returns null for a command this file
 * does not declare — a page and a brain ship separately, and an older page
 * receiving a newer action should ignore it, not throw.
 */
export function asUiAction(command: string, payload: unknown): UiAction | null {
  return _known.has(command) ? ({ command, payload } as UiAction) : null;
}

/**
 * Call this in a `switch`'s default arm. Adding an action then fails to
 * compile here until the new case is handled — which is the whole point of
 * generating this file.
 */
export function unhandledUiAction(action: never): never {
  throw new Error(`Unhandled action: ${JSON.stringify(action)}`);
}
