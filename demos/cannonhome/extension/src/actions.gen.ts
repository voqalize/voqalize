// Generated from cannonhome/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types cannonhome/backend/brain.py -o cannonhome/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/** Bring one of the visitor's Cannon Home tabs to the front. */
export interface FocusTab {
  tab_id: string;
}

/**
 * The call's language moved, by the toggle, by voice or by
 * `set_language`: the widget's toggle follows at once.
 */
export interface LanguageChanged {
  language: 'en' | 'es';
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

/** The visitor's cart, after an add (whoever made it) or when shown. */
export interface CartState {
  items?: CartItem[];

  count?: number;

  subtotal?: number | null;

  free_shipping_left?: number | null;
}

/**
 * The checkout's delivery form (/checkout, the guest's one-page checkout):
 * on load and after each change, whoever made it (debounced by the page).
 *
 * **Names, not values.** What the visitor typed stays on their screen: the
 * form reports which fields hold something, never what, apart from the
 * región and comuna chosen (the site's own option names). The RUT, any
 * password and anything of the payment step are never read at all; `rut`
 * is named in `filled` or `missing` only so he knows whether they have
 * typed it.
 */
export interface CheckoutState {
  filled?: string[];

  missing?: string[];

  invalid?: CheckoutInvalid[];

  region?: string;

  comuna?: string;

  email_has_account?: boolean;

  delivery_options?: string[];

  delivery?: string;

  payment_open?: boolean;
}

/** The visitor pressed the other language on the widget's toggle. */
export interface LanguageRequested {
  language: 'en' | 'es';
}

/** A category or search listing is in front, after a load or a filter. */
export interface ListingShown {
  path: string;

  title?: string;

  count?: number | null;

  filters?: Record<string, string>;

  sort?: string;

  items?: ListingItem[];
}

/** The tab in front changed page, or came to the front: what is on it now. */
export interface PageChanged {
  site?: string;

  url?: string;

  path: string;

  title?: string;

  kind?: 'home' | 'category' | 'search' | 'product' | 'cart' | 'checkout' | 'page';

  headings?: string[];

  faqs?: string[];

  plans?: string[];
}

/**
 * The live prices and stock `check_prices` asked for, from the store's
 * GraphQL. `missing` are the paths it could not find.
 */
export interface PricesRead {
  items?: PriceItem[];

  missing?: string[];
}

/**
 * A product page is in front: what it shows, read in the visitor's
 * browser. Sent on load from the page (`source` `page`: the HTML may be
 * hours old) and again once the store's GraphQL confirms it (`graphql`,
 * live): the second one wins.
 */
export interface ProductShown {
  path: string;

  sku?: string;

  name?: string;

  price?: number | null;

  regular_price?: number | null;

  in_stock?: boolean | null;

  qty?: number | null;

  specs?: Record<string, string>;

  rating?: number | null;

  reviews?: number | null;

  source?: 'page' | 'graphql';
}

/** The search box's suggestions for what was typed in it. */
export interface SearchSuggest {
  query: string;

  items?: SuggestItem[];

  categories?: string[];
}

/** Every Cannon Home tab the visitor has open, and the one in front. */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

export interface CartItem {
  name: string;

  path?: string;

  qty?: number;

  price?: number | null;
}

export interface CheckoutInvalid {
  field: string;

  message?: string;
}

export interface ListingItem {
  name: string;

  path: string;

  price?: number | null;

  regular_price?: number | null;
}

export interface PriceItem {
  path: string;

  sku?: string;

  name?: string;

  price?: number | null;

  regular_price?: number | null;

  in_stock?: boolean | null;

  qty?: number | null;
}

/** One argument the page could not use, and what it offers instead. */
export interface Refusal {
  arg: string;

  why: string;

  options?: string[];
}

export interface SuggestItem {
  name: string;

  path: string;

  price?: number | null;
}

export interface TabInfo {
  tab_id: string;

  url?: string;

  title?: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'focus_tab',
  'language_changed',
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
  | { event: 'stage_hello'; payload: StageHello }
  | { event: 'stage_progress'; payload: StageProgress }
  | { event: 'stage_result'; payload: StageResult }
  | { event: 'cart_state'; payload: CartState }
  | { event: 'checkout_state'; payload: CheckoutState }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'listing_shown'; payload: ListingShown }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'prices_read'; payload: PricesRead }
  | { event: 'product_shown'; payload: ProductShown }
  | { event: 'search_suggest'; payload: SearchSuggest }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'stage_hello',
  'stage_progress',
  'stage_result',
  'cart_state',
  'checkout_state',
  'language_requested',
  'listing_shown',
  'page_changed',
  'prices_read',
  'product_shown',
  'search_suggest',
  'tabs_changed',
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
