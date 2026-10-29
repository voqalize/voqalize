// Generated from agroplanet/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types agroplanet/backend/brain.py -o agroplanet/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/** Bring one of the visitor's Agroplanet tabs to the front. */
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

/**
 * Which tractors the store's catalogue lists a part for, as
 * `check_fit` read it (`product/getPartAppRecords`): the product page
 * shows none of it. `universal` when the catalogue lists it as UNIVERSAL
 * (a generic part, for no one machine); no `brands` when it lists no
 * machine at all. With a machine asked (`brand`, `model`, `year`),
 * `matched` says whether the catalogue lists it, `match` what it
 * matched and `missing` what it did not.
 */
export interface FitRead {
  path: string;

  sku?: string;

  name?: string;

  universal?: boolean;

  brands?: FitBrand[];

  total?: number | null;

  brand?: string | null;

  model?: string | null;

  year?: string | null;

  matched?: boolean | null;

  match?: string | null;

  missing?: string | null;
}

/** The visitor pressed the other language on the widget's toggle. */
export interface LanguageRequested {
  language: 'en' | 'es';
}

/**
 * The tab in front changed page, or came to the front: what is on it now.
 *
 * Agroplanet is one Angular app, so this fires on every route change inside
 * it as well as on a load.
 */
export interface PageChanged {
  site?: string;

  url?: string;

  path: string;

  title?: string;

  kind?: 'home' | 'category' | 'search' | 'brand' | 'product' | 'cart' | 'quote' | 'stores' | 'policy' | 'page';

  headings?: string[];

  faqs?: string[];
}

/**
 * The live prices and stock `check_prices` asked for. `missing`
 * are the paths the store could not read.
 */
export interface PricesRead {
  items?: PriceItem[];

  missing?: string[];
}

/**
 * What `find_products` read from the store's own catalogue search: up to
 * eight products with their live prices and stock, and how many match.
 */
export interface ProductsFound {
  query?: string | null;

  category_code?: string | null;

  brand?: string | null;

  total?: number | null;

  suggestion?: string | null;

  retried_with?: string | null;

  items?: FoundItem[];
}

/**
 * One product's stock online and in the stores that report it, as
 * `check_stock` read it; `asked` is the store the visitor asked about,
 * `matched` the store's name it matched, if any.
 */
export interface StockRead {
  path: string;

  sku?: string;

  name?: string;

  online?: 'inStock' | 'lowStock' | 'outOfStock' | '';

  online_level?: number | null;

  stores?: StoreStock[];

  asked?: string | null;

  matched?: string | null;
}

/** A store's card on /nuestras-tiendas, rung by `stores.show`. */
export interface StoreShown {
  name: string;

  address?: string;

  city?: string;

  phone?: string;

  hours?: string;
}

/** Every Agroplanet tab the visitor has open, and the one in front. */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

/** One make the part is listed for, with as much below it as was read. */
export interface FitBrand {
  brand: string;

  count?: number | null;

  models?: string[];

  years?: string[];

  engines?: string[];
}

export interface FoundItem {
  path: string;

  sku?: string;

  name?: string;

  brand?: string;

  price?: number | null;

  regular_price?: number | null;

  discount?: number | null;

  offer_price?: number | null;

  price_hidden?: boolean;

  stock?: 'inStock' | 'lowStock' | 'outOfStock' | '';

  stock_level?: number | null;
}

export interface PriceItem {
  path: string;

  sku?: string;

  name?: string;

  price?: number | null;

  regular_price?: number | null;

  discount?: number | null;

  offer_price?: number | null;

  price_hidden?: boolean;

  stock?: 'inStock' | 'lowStock' | 'outOfStock' | '';

  stock_level?: number | null;
}

/** One argument the page could not use, and what it offers instead. */
export interface Refusal {
  arg: string;

  why: string;

  options?: string[];
}

export interface StoreStock {
  name: string;

  city?: string;

  qty?: number | null;

  status?: 'inStock' | 'lowStock' | 'outOfStock' | '';
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
  | { event: 'stage_event'; payload: StageEvent }
  | { event: 'stage_hello'; payload: StageHello }
  | { event: 'stage_progress'; payload: StageProgress }
  | { event: 'stage_result'; payload: StageResult }
  | { event: 'fit_read'; payload: FitRead }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'prices_read'; payload: PricesRead }
  | { event: 'products_found'; payload: ProductsFound }
  | { event: 'stock_read'; payload: StockRead }
  | { event: 'store_shown'; payload: StoreShown }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'stage_event',
  'stage_hello',
  'stage_progress',
  'stage_result',
  'fit_read',
  'language_requested',
  'page_changed',
  'prices_read',
  'products_found',
  'stock_read',
  'store_shown',
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
