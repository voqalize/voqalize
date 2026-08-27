// Generated from shopping/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types shopping/backend/brain.py -o shopping/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

export interface ShowSearch {
  query: string;

  brand: string | null;

  max_price: number | null;

  category: 'flagship' | 'mid-range' | 'budget' | null;

  sort_by: 'price_low' | 'price_high' | 'rating' | 'newest' | null;

  result_ids: string[];
}

export interface OpenProduct {
  /** The id of the phone to open. */
  product_id: string;
}

export interface ApplyFilters {
  brand: string | null;

  max_price: number | null;

  min_price: number | null;

  category: 'flagship' | 'mid-range' | 'budget' | null;

  result_ids: string[];
}

export type ClearFilters = Record<string, never>;

export type NavigateHome = Record<string, never>;

export interface Highlight {
  /** The phone whose section to highlight. */
  product_id: string;

  /** Which spec section to highlight. */
  feature: 'display' | 'camera' | 'battery' | 'performance' | 'charging' | 'colors' | 'specs' | 'reviews';
}

export interface Compare {
  product_ids: string[];
}

export interface AddToCart {
  product_id: string;

  cart_count: number;
}

export interface Sort {
  /** 'price_low' (cheapest first), 'price_high' (most expensive first), 'rating' (top rated first), or 'newest'. */
  sort_by: 'price_low' | 'price_high' | 'rating' | 'newest';
}

export interface AddToWishlist {
  product_id: string;

  wishlist_count: number;
}

export interface OpenFaq {
  /** Which policy topic to scroll to. */
  topic: 'shipping' | 'returns' | 'warranty' | 'payment' | 'trade-in' | 'price-match' | 'activation' | null;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'show_search'; payload: ShowSearch }
  | { command: 'open_product'; payload: OpenProduct }
  | { command: 'apply_filters'; payload: ApplyFilters }
  | { command: 'clear_filters'; payload: ClearFilters }
  | { command: 'navigate_home'; payload: NavigateHome }
  | { command: 'highlight'; payload: Highlight }
  | { command: 'compare'; payload: Compare }
  | { command: 'add_to_cart'; payload: AddToCart }
  | { command: 'sort'; payload: Sort }
  | { command: 'add_to_wishlist'; payload: AddToWishlist }
  | { command: 'open_faq'; payload: OpenFaq };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'show_search',
  'open_product',
  'apply_filters',
  'clear_filters',
  'navigate_home',
  'highlight',
  'compare',
  'add_to_cart',
  'sort',
  'add_to_wishlist',
  'open_faq',
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
