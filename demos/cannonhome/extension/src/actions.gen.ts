// Generated from cannonhome/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types cannonhome/backend/brain.py -o cannonhome/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * A move for the page to make when the voice reaches `at` — the first
 * words of the sentence it belongs to (see `.cues`); empty `at` is
 * when the voice stops. With `path`, open that page of cannonhome.cl first
 * (a full load); then `heading` scrolls to that heading and rings it,
 * `text` rings the smallest element with those words, `faq` opens that FAQ.
 */
export interface Cue {
  at: string;

  word: number;

  path: string | null;

  heading: string | null;

  text: string | null;

  faq: string | null;
}

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

/**
 * Type `query` into the store's search box (`input.amsearch-input`) at a
 * human pace and let its suggestions open; report `search_suggest`. With
 * `open_index` (0-based: 0 is the first suggested product), open that
 * product: the page then reports `product_shown`.
 */
export interface SearchProducts {
  query: string;

  open_index: number | null;
}

/**
 * Go to the listing at `category_path` (a full load, if it is not the one
 * in front), then apply each filter given with its quick-filter pill — the
 * option labels exactly as the listing writes them ("2 Plazas", "Blanco",
 * "300", "100% Algodón") — one at a time, waiting for the grid; then the sort.
 * Reports `listing_shown`.
 */
export interface FilterListing {
  category_path: string;

  size: string | null;

  color: string | null;

  threads: string | null;

  material: string | null;

  sort: 'price_asc' | 'price_desc' | 'relevance' | 'newest' | null;
}

/**
 * Open the product at `path` (`/x.html`; a full load), then the tab
 * named, or step through its photos for `fotos`. Reports `product_shown`.
 */
export interface OpenProduct {
  path: string;

  tab: 'descripcion' | 'especificaciones' | 'calificaciones' | 'fotos' | null;
}

/**
 * Read the live price and stock of these products (at most six), with one
 * same-origin POST to the store's GraphQL. Moves nothing. Reports `prices_read`.
 */
export interface CheckPrices {
  paths: string[];
}

/**
 * On the product page at `path` (opened first if it is not in front), set
 * the quantity to `qty` and press Agregar; wait for the cart drawer.
 * Reports `cart_state`. Never the checkout.
 */
export interface AddToCart {
  path: string;

  qty: number;
}

/** Open the cart drawer (`open`), or close it. Never the checkout. */
export interface ShowCart {
  open: boolean;
}

/**
 * Set the cart line of the product at `path` to `qty`, or take it
 * out with 0: in the cart drawer with its own minus and plus, or its bin and
 * "Aceptar"; on the cart page (/checkout/cart) with the request those send,
 * then the reload the page's own controls make, the move checked on the page
 * it loads. Reports `cart_state`. Never the checkout.
 */
export interface UpdateCartItem {
  path: string;

  qty: number;
}

/**
 * Take the visitor to the guest checkout's delivery form: on the bag
 * (/checkout/cart/, loaded first if it is not in front) press "Terminar
 * pedido", then, in the window it opens, "Comprar como invitado" — never its
 * login, Google or "Crear Cuenta" — and wait for the form (/checkout).
 * Reports `checkout_state`. Nothing past the form.
 */
export type StartCheckout = Record<string, never>;

/**
 * Fill the checkout's delivery form with what the visitor said (the
 * guest checkout is opened first, as `StartCheckout`, if it is not
 * in front). Only the fields given, each set as a finished edit: región and
 * comuna picked from the site's own lists (the comuna's list loads after the
 * región). There is no RUT, password or payment field here, and the page
 * refuses every one of them. Never presses anything after the fields.
 * Reports `checkout_state`.
 */
export interface FillCheckout {
  email: string | null;

  first_name: string | null;

  last_name: string | null;

  phone: string | null;

  region: string | null;

  comuna: string | null;

  street: string | null;

  number: string | null;

  apartment: string | null;
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

/** A move Javier sent was carried out: the page now shows what he asked. */
export interface CommandDone {
  command: string;

  detail?: string;
}

/** A move Javier sent could not be carried out on the page. */
export interface CommandFailed {
  command: string;

  error?: string;

  reason?: string;
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
  | { command: 'cue'; payload: Cue }
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged }
  | { command: 'search_products'; payload: SearchProducts }
  | { command: 'filter_listing'; payload: FilterListing }
  | { command: 'open_product'; payload: OpenProduct }
  | { command: 'check_prices'; payload: CheckPrices }
  | { command: 'add_to_cart'; payload: AddToCart }
  | { command: 'show_cart'; payload: ShowCart }
  | { command: 'update_cart_item'; payload: UpdateCartItem }
  | { command: 'start_checkout'; payload: StartCheckout }
  | { command: 'fill_checkout'; payload: FillCheckout };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'cue',
  'focus_tab',
  'language_changed',
  'search_products',
  'filter_listing',
  'open_product',
  'check_prices',
  'add_to_cart',
  'show_cart',
  'update_cart_item',
  'start_checkout',
  'fill_checkout',
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
  | { event: 'cart_state'; payload: CartState }
  | { event: 'checkout_state'; payload: CheckoutState }
  | { event: 'command_done'; payload: CommandDone }
  | { event: 'command_failed'; payload: CommandFailed }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'listing_shown'; payload: ListingShown }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'prices_read'; payload: PricesRead }
  | { event: 'product_shown'; payload: ProductShown }
  | { event: 'search_suggest'; payload: SearchSuggest }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'cart_state',
  'checkout_state',
  'command_done',
  'command_failed',
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
