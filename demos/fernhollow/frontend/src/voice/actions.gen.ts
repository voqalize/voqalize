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

/** Ring a checkout input and set it. */
export interface CheckoutFill {
  field: 'email' | 'first_name' | 'last_name' | 'address1' | 'address2' | 'city' | 'region' | 'postcode' | 'country' | 'phone' | 'delivery';

  value: string;
}

/** Move the checkout to a step. */
export interface CheckoutStep {
  step: 'contact' | 'shipping' | 'review';
}

/** The confirm prompt on Place order. */
export interface ConfirmPlaceOrder {
  total: number;

  label: string;
}

/** The confirmation page, with the demo order's number. */
export interface OrderPlaced {
  order_number: string;

  total: number;
}

/** Numbered badges 1..n on these product cards (2-4, all on screen). */
export interface ShowChoices {
  product_ids: string[];

  label: string;
}

/** The choice badges removed. */
export type ClearChoices = Record<string, never>;

/** The circled selection's badges and chip removed. */
export type ClearSelection = Record<string, never>;

/** Revert the last screen-changing action. */
export type Undo = Record<string, never>;

/**
 * A named act that changed one slice of the page's state
 * (`cart.changed`, `listing.filtered`), as the app's Stage Spec declares
 * it. Only the fields the slice declares, and none it marks private, are
 * sent; the brain folds them into its mirror and tells the model one short
 * line, never the values.
 */
export interface StageEvent {
  name: string;

  by?: 'visitor' | 'agent';

  data?: Record<string, unknown>;

  call_ref?: string | null;
}

/** A page running Stage, saying what it is — on connect and on every load. */
export interface StageHello {
  runtime: string;

  contract: number;

  url?: string;

  title?: string;
}

/**
 * Where a move is, before its result: never final, sent as its phase
 * changes. Each one tells the brain the move is alive, so a move that is
 * slow is not taken for one that failed.
 */
export interface StageProgress {
  call_ref: string;

  move: string;

  phase: 'queued' | 'loading' | 'waiting_site' | 'ringing' | 'acting' | 'confirming';

  ms?: number;
}

/** What happened to one move: sent exactly once per `call_ref`. */
export interface StageResult {
  call_ref: string;

  move: string;

  outcome: 'applied' | 'partial' | 'refused' | 'failed' | 'undone' | 'unknown';

  detail?: string | null;

  refused?: Refusal[];

  moved?: boolean;

  ms?: number;

  fired?: 'anchor' | 'fuzzy' | 'clock' | 'end' | 'now' | 'quiet' | null;

  received_ms?: number | null;

  queued_ms?: number | null;

  fired_ms?: number | null;

  ringed_ms?: number | null;

  lag_ms?: number | null;

  late?: boolean;
}

/** The cart as it now stands, after the shopper changed it. */
export interface CartChanged {
  lines?: CartLineIn[];

  total?: number;

  by?: string;
}

/** The shopper filled or changed a checkout field — its name, never its value. */
export interface CheckoutChanged {
  field?: string;

  by?: string;
}

/** The checkout moved to a step: contact, shipping or review. */
export interface CheckoutStepReached {
  step?: string;

  by?: string;
}

/** The shopper clicked one of the numbered products Emily asked between. */
export interface ChoiceMade {
  product_id?: string;

  by?: string;
}

/**
 * The shopper's answer on a confirmation: Add to cart, or Place order —
 * which carries the order number the page used.
 */
export interface ConfirmResult {
  confirmed?: boolean;

  order_number?: string | null;

  by?: string;
}

/** The shopper changed the filter chips. */
export interface FilterChanged {
  filters?: FiltersIn;

  by?: string;
}

/**
 * A listing page (room, category, sale, search) as it stands: its rail's
 * facets and values (the rail's own labels), what is ticked, the price range,
 * the sort and the count. Sent on arrival and on every change. Silent.
 */
export interface ListingViewed {
  page?: string;

  title?: string;

  facets?: Record<string, string[]>;

  active?: Record<string, string[]>;

  price?: PriceIn | null;

  sort?: string;

  count?: number;

  by?: string;
}

/** The orders the page holds — on connect and whenever the list changes. Silent. */
export interface OrdersKnown {
  orders?: OrderIn[];

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

/**
 * The product card or page under the shopper's pointer, finger or keyboard
 * focus (debounced). Kept for "this one"; never spoken about.
 */
export interface Pointing {
  product_id?: string;

  how?: string;

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

/**
 * The shopper circled things on screen (Show Emily: circle to ask). Kept
 * until cleared, across pages; acted on only when they speak about it.
 */
export interface Selection {
  things?: ThingIn[];

  gesture?: string;

  page?: string;

  by?: string;
}

/** The circled selection was cleared (its clear button, Esc, or a new circle). */
export interface SelectionCleared {
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

/**
 * The products the grid or strip now shows, in screen order, with where
 * each sits — so "the left one" and "the bottom row" resolve.
 */
export interface VisibleProducts {
  product_ids?: string[];

  layout?: LayoutIn[];

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

/** Where one visible product sits: row and column from the top left. */
export interface LayoutIn {
  product_id: string;

  row?: number;

  col?: number;
}

export interface MoreLikeItem {
  product_id: string;

  differences: string[];
}

/** One order the page holds (a placed order counts as delivered when placed). */
export interface OrderIn {
  number?: string;

  email?: string;

  name?: string;

  placed_at?: string;

  lines?: OrderLineIn[];

  total?: number;

  status?: string;

  placed_days_ago?: number;

  delivered_days_ago?: number | null;
}

export interface OrderLineIn {
  product_id: string;

  variant_id?: string;

  title?: string;

  variant?: string;

  qty?: number;

  unit_price?: number;
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

export interface PriceIn {
  min?: number | null;

  max?: number | null;
}

/** One argument the page could not use, and what it offers instead. */
export interface Refusal {
  arg: string;

  why: string;

  options?: string[];
}

export interface SavingSwap {
  slot: string;

  from_id: string;

  to_id: string;

  was: number;

  now: number;
}

/** One thing the shopper circled: a product, category, room or article. */
export interface ThingIn {
  kind?: string;

  id?: string;
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
  | { command: 'checkout_fill'; payload: CheckoutFill }
  | { command: 'checkout_step'; payload: CheckoutStep }
  | { command: 'confirm_place_order'; payload: ConfirmPlaceOrder }
  | { command: 'order_placed'; payload: OrderPlaced }
  | { command: 'show_choices'; payload: ShowChoices }
  | { command: 'clear_choices'; payload: ClearChoices }
  | { command: 'clear_selection'; payload: ClearSelection }
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
  'checkout_fill',
  'checkout_step',
  'confirm_place_order',
  'order_placed',
  'show_choices',
  'clear_choices',
  'clear_selection',
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
  | { event: 'stage_event'; payload: StageEvent }
  | { event: 'stage_hello'; payload: StageHello }
  | { event: 'stage_progress'; payload: StageProgress }
  | { event: 'stage_result'; payload: StageResult }
  | { event: 'cart_changed'; payload: CartChanged }
  | { event: 'checkout_changed'; payload: CheckoutChanged }
  | { event: 'checkout_step_reached'; payload: CheckoutStepReached }
  | { event: 'choice_made'; payload: ChoiceMade }
  | { event: 'confirm_result'; payload: ConfirmResult }
  | { event: 'filter_changed'; payload: FilterChanged }
  | { event: 'listing_viewed'; payload: ListingViewed }
  | { event: 'orders_known'; payload: OrdersKnown }
  | { event: 'page_viewed'; payload: PageViewed }
  | { event: 'pointing'; payload: Pointing }
  | { event: 'product_viewed'; payload: ProductViewed }
  | { event: 'room_board_edited'; payload: RoomBoardEdited }
  | { event: 'selection'; payload: Selection }
  | { event: 'selection_cleared'; payload: SelectionCleared }
  | { event: 'shortlist_changed'; payload: ShortlistChanged }
  | { event: 'variant_selected'; payload: VariantSelected }
  | { event: 'visible_products'; payload: VisibleProducts };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'stage_event',
  'stage_hello',
  'stage_progress',
  'stage_result',
  'cart_changed',
  'checkout_changed',
  'checkout_step_reached',
  'choice_made',
  'confirm_result',
  'filter_changed',
  'listing_viewed',
  'orders_known',
  'page_viewed',
  'pointing',
  'product_viewed',
  'room_board_edited',
  'selection',
  'selection_cleared',
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
