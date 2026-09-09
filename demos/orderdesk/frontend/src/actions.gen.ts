// Generated from orderdesk/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types orderdesk/backend/brain.py -o orderdesk/frontend/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

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

/**
 * He picked a brand card. Not the same act as answering a question — nobody
 * asked — and the next thing to say differs accordingly.
 */
export interface FamilyChosen {
  item_id: string;

  family: string;

  surviving_codes?: string[];
}

/** He tapped Confirm. The call is over bar the goodbye. */
export interface OrderConfirmed {
  order_no?: string;

  item_count?: number;

  total_mrp?: number;
}

/** He typed or stepped a quantity. */
export interface QuantitySet {
  item_id: string;

  quantity: number;
}

/**
 * He answered the question on the row by tapping a pill. `question` is what
 * was asked, so a model about to ask it again can see that it is spent.
 */
export interface QuestionAnswered {
  item_id: string;

  question?: string;

  answer?: string;

  surviving_codes?: string[];
}

/**
 * He added a row himself, out of the search panel — a row the mirror has
 * never seen and every tool would otherwise be blind to.
 */
export interface RowAdded {
  item_id: string;

  sku_code: string;

  sku_name?: string;

  query?: string;

  quantity?: number | null;
}

/**
 * He deleted a row. Carries its name because after this the mirror has
 * nothing left to look the name up from.
 */
export interface RowRemoved {
  item_id: string;

  spoken_text?: string;
}

/**
 * He pointed at one medicine for this row — off the pills, out of the variant
 * strip, or out of the search panel. `via` is not decoration: "picked it off
 * the options I offered" and "swapped the variant on a row that was already
 * settled" are different things to say back to him.
 */
export interface SkuChosen {
  item_id: string;

  sku_code: string;

  sku_name?: string;

  via?: 'pill' | 'variant' | 'search';
}

// ── Shapes used by the messages above ──────────────────────────────

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

/** Everything the person can do on screen, discriminated by `event`. */
export type AppEvent =
  | { event: 'family_chosen'; payload: FamilyChosen }
  | { event: 'order_confirmed'; payload: OrderConfirmed }
  | { event: 'quantity_set'; payload: QuantitySet }
  | { event: 'question_answered'; payload: QuestionAnswered }
  | { event: 'row_added'; payload: RowAdded }
  | { event: 'row_removed'; payload: RowRemoved }
  | { event: 'sku_chosen'; payload: SkuChosen };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'family_chosen',
  'order_confirmed',
  'quantity_set',
  'question_answered',
  'row_added',
  'row_removed',
  'sku_chosen',
];

/**
 * Send one thing the person did. `send` is a pipecat client's `sendUIEvent`,
 * or null before the call connects — a gesture made off-call is dropped,
 * which is right: there is no brain that missed it.
 *
 * The name picks the payload type, so a field renamed in Python stops
 * compiling here rather than arriving as a shape the brain discards.
 */
export function sendAppEvent(
  send: ((event: string, payload?: unknown) => void) | null | undefined,
  event: AppEvent,
): void {
  send?.(event.event, event.payload);
}
