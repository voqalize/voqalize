// Generated from fernhollow/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types fernhollow/backend/brain.py -o fernhollow/frontend/src/voice/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Route change: home | room/<room> | category/<slug> | product/<id> |
 * journal | journal/<slug> | cart | policy/<topic>.
 */
export interface Navigate {
  page: string;
}

/** A listing grid with these products. */
export interface ShowProducts {
  title: string;

  query: string;

  product_ids: string[];

  count: number;
}

/** Filter chips + grid; `assumption` is what a broad word was read as. */
export interface ApplyFilters {
  filters: FiltersOut;

  product_ids: string[];

  count: number;

  assumption: string | null;
}

/**
 * One chip removed: `key` is a filter key, or `key:value` for one value
 * of a list filter (`materials:oak`).
 */
export interface RemoveFilter {
  key: string;

  product_ids: string[];

  count: number;
}

/** The product page, with its focus section ringed. */
export interface OpenProduct {
  product_id: string;

  variant_id: string | null;

  focus: 'options' | 'highlights' | 'price' | null;
}

/** The variant picker set and ringed. */
export interface SelectVariant {
  product_id: string;

  variant_id: string;
}

/**
 * A 300 ms spotlight ring: product:<id> | filter:<key> | slot:<slot> |
 * button:add-to-cart | section:<name>.
 */
export interface Highlight {
  target: string;
}

/** The room-brief chips. */
export interface UpdateBrief {
  brief: BriefOut;

  products_left: number;
}

/** The room board; pieces appear one by one. */
export interface ShowRoomSet {
  room: string;

  budget: number | null;

  total: number;

  pieces: PieceOut[];
}

/** One room-board tile changes. */
export interface SwapPiece {
  slot: string;

  old_product_id: string;

  piece: PieceOut;

  total: number;
}

/** The compare board. */
export interface ShowCompare {
  product_ids: string[];

  rows: CompareRow[];

  summary: string;
}

/** The goes-with strip. */
export interface ShowGoesWith {
  anchor_id: string;

  items: GoesWithItem[];
}

/** The look-alike strip, with difference badges. */
export interface ShowMoreLike {
  anchor_id: string;

  items: MoreLikeItem[];
}

/**
 * Savings badges on the room board; `moved_to` is the slot the saving
 * went to.
 */
export interface ShowSavings {
  swaps: SavingSwap[];

  saved: number;

  moved_to: string | null;
}

/** The shortlist tray. */
export interface UpdateShortlist {
  product_ids: string[];
}

/** The confirm prompt on the Add button. */
export interface ConfirmAdd {
  lines: ConfirmLine[];

  label: string;
}

/** The cart drawer opens with these lines. */
export interface CartUpdated {
  lines: CartLine[];

  total: number;

  saved: number;
}

/** A suggestion card in the cart. */
export interface SuggestFinish {
  product_id: string;

  reason: string;
}

/** The policy panel. */
export interface OpenPolicy {
  topic: 'returns' | 'delivery' | 'assembly' | 'care';
}

/** Revert the last screen-changing action. */
export type Undo = Record<string, never>;

/** The cart as it now stands, after the shopper changed it. */
export interface CartChanged {
  lines?: CartLineIn[];

  total?: number;

  by?: string;
}

/** The shopper's answer on the Add-to-cart confirmation. */
export interface ConfirmResult {
  confirmed?: boolean;

  by?: string;
}

/** The shopper changed the filter chips. */
export interface FilterChanged {
  filters?: FiltersIn;

  by?: string;
}

/**
 * The shopper opened a page (`home`, `room/<room>`, `category/<slug>`,
 * `product/<id>`, `journal`, `cart`, `policy/<topic>`…).
 */
export interface PageViewed {
  path?: string;

  by?: string;
}

/** The shopper opened a product page. */
export interface ProductViewed {
  product_id?: string;

  variant_id?: string | null;

  by?: string;
}

/** The shopper removed or locked a tile on the room board. */
export interface RoomBoardEdited {
  slot?: string;

  action?: string;

  by?: string;
}

/** The shortlist tray as it now stands. */
export interface ShortlistChanged {
  product_ids?: string[];

  by?: string;
}

/** The shopper picked an option value on a product. */
export interface VariantSelected {
  product_id?: string;

  variant_id?: string;

  by?: string;
}

/** The products the grid or strip now shows, in screen order. */
export interface VisibleProducts {
  product_ids?: string[];

  by?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

export interface BriefOut {
  room: string | null;

  uses: string[];

  materials: string[];

  colours: string[];

  styles: string[];

  budget: number | null;
}

export interface CartLine {
  product_id: string;

  variant_id: string;

  qty: number;

  title: string;

  price: number;

  image: string;
}

/** One cart line as the page holds it. */
export interface CartLineIn {
  product_id: string;

  variant_id?: string | null;

  qty?: number;
}

export interface CompareRow {
  label: string;

  values: string[];

  winner: number | null;
}

export interface ConfirmLine {
  product_id: string;

  variant_id: string;

  qty: number;
}

/** The filter chips as the page now holds them. */
export interface FiltersIn {
  room?: string | null;

  category?: string | null;

  materials?: string[];

  colours?: string[];

  styles?: string[];

  price_min?: number | null;

  price_max?: number | null;

  on_sale?: boolean | null;
}

/** The filter chips. */
export interface FiltersOut {
  room: string | null;

  category: string | null;

  materials: string[];

  colours: string[];

  styles: string[];

  price_min: number | null;

  price_max: number | null;

  on_sale: boolean | null;
}

export interface GoesWithItem {
  product_id: string;

  reason: string;
}

export interface MoreLikeItem {
  product_id: string;

  differences: string[];
}

/** One room-board tile. */
export interface PieceOut {
  slot: string;

  product_id: string;

  variant_id: string;

  title: string;

  price: number;

  compare_at: number | null;

  image: string;

  reason: string;
}

export interface SavingSwap {
  slot: string;

  from_id: string;

  to_id: string;

  was: number;

  now: number;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'navigate'; payload: Navigate }
  | { command: 'show_products'; payload: ShowProducts }
  | { command: 'apply_filters'; payload: ApplyFilters }
  | { command: 'remove_filter'; payload: RemoveFilter }
  | { command: 'open_product'; payload: OpenProduct }
  | { command: 'select_variant'; payload: SelectVariant }
  | { command: 'highlight'; payload: Highlight }
  | { command: 'update_brief'; payload: UpdateBrief }
  | { command: 'show_room_set'; payload: ShowRoomSet }
  | { command: 'swap_piece'; payload: SwapPiece }
  | { command: 'show_compare'; payload: ShowCompare }
  | { command: 'show_goes_with'; payload: ShowGoesWith }
  | { command: 'show_more_like'; payload: ShowMoreLike }
  | { command: 'show_savings'; payload: ShowSavings }
  | { command: 'update_shortlist'; payload: UpdateShortlist }
  | { command: 'confirm_add'; payload: ConfirmAdd }
  | { command: 'cart_updated'; payload: CartUpdated }
  | { command: 'suggest_finish'; payload: SuggestFinish }
  | { command: 'open_policy'; payload: OpenPolicy }
  | { command: 'undo'; payload: Undo };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'show_products',
  'apply_filters',
  'remove_filter',
  'open_product',
  'select_variant',
  'highlight',
  'update_brief',
  'show_room_set',
  'swap_piece',
  'show_compare',
  'show_goes_with',
  'show_more_like',
  'show_savings',
  'update_shortlist',
  'confirm_add',
  'cart_updated',
  'suggest_finish',
  'open_policy',
  'undo',
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
  | { event: 'cart_changed'; payload: CartChanged }
  | { event: 'confirm_result'; payload: ConfirmResult }
  | { event: 'filter_changed'; payload: FilterChanged }
  | { event: 'page_viewed'; payload: PageViewed }
  | { event: 'product_viewed'; payload: ProductViewed }
  | { event: 'room_board_edited'; payload: RoomBoardEdited }
  | { event: 'shortlist_changed'; payload: ShortlistChanged }
  | { event: 'variant_selected'; payload: VariantSelected }
  | { event: 'visible_products'; payload: VisibleProducts };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'cart_changed',
  'confirm_result',
  'filter_changed',
  'page_viewed',
  'product_viewed',
  'room_board_edited',
  'shortlist_changed',
  'variant_selected',
  'visible_products',
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
