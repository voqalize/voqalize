/**
 * MobileShopStore — the single source of truth for the demo's screen state.
 *
 * Both the human (tapping the UI) and the Mobile Expert agent (via `ui-command`
 * RTVI events) call the SAME actions, so the screen stays consistent no
 * matter who is driving. Navigation is plain React state — never the router —
 * so the `PipecatClient` mounted alongside never unmounts and the call stays
 * live as the shopper moves between pages.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  filterCatalog,
  getPhone,
  sortPhones,
  type CatalogFilters,
  type Phone,
  type SortKey,
} from './catalog';

export type View = 'home' | 'search' | 'product' | 'compare' | 'faq';

export interface Filters {
  brand?: string;
  maxPrice?: number;
  minPrice?: number;
  category?: string;
}

export interface Highlight {
  productId: string;
  feature: string;
  nonce: number; // bump to retrigger the same highlight
}

interface State {
  view: View;
  productId: string | null;
  compareIds: string[];
  query: string;
  filters: Filters;
  sortBy: SortKey | undefined;
  cart: string[];
  wishlist: string[];
  faqTopic: string | null;
  highlight: Highlight | null;
}

const INITIAL: State = {
  view: 'home',
  productId: null,
  compareIds: [],
  query: '',
  filters: {},
  sortBy: undefined,
  cart: [],
  wishlist: [],
  faqTopic: null,
  highlight: null,
};

export interface MobileShopActions {
  goHome: () => void;
  showSearch: (opts?: {
    query?: string;
    brand?: string;
    maxPrice?: number;
    category?: string;
    sort?: SortKey;
  }) => void;
  openProduct: (id: string) => void;
  applyFilters: (f: Filters) => void;
  setQuery: (q: string) => void;
  toggleBrand: (brand: string) => void;
  setMaxPrice: (max: number | undefined) => void;
  setCategory: (cat: string | undefined) => void;
  setSort: (by: SortKey | undefined) => void;
  clearFilters: () => void;
  highlightFeature: (productId: string, feature: string) => void;
  compare: (ids: string[]) => void;
  addToCart: (id: string) => void;
  toggleWishlist: (id: string) => void;
  addToWishlist: (id: string) => void;
  openFaq: (topic?: string | null) => void;
}

export interface MobileShopStore extends State, MobileShopActions {
  results: Phone[];
  cartPhones: Phone[];
  wishlistPhones: Phone[];
  /** Dispatch a `ui-command` RTVI event's `{ command, payload }` from the agent. */
  handleUiCommand: (command: string, payload: Record<string, unknown>) => void;
}

const Ctx = createContext<MobileShopStore | null>(null);

export function MobileShopProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(INITIAL);

  const goHome = useCallback(() => {
    setState((s) => ({ ...s, view: 'home', highlight: null }));
  }, []);

  const showSearch = useCallback(
    (opts?: { query?: string; brand?: string; maxPrice?: number; category?: string; sort?: SortKey }) => {
      setState((s) => ({
        ...s,
        view: 'search',
        query: opts?.query ?? '',
        filters: {
          brand: opts?.brand,
          maxPrice: opts?.maxPrice,
          category: opts?.category,
        },
        sortBy: opts?.sort ?? s.sortBy,
        highlight: null,
      }));
    },
    [],
  );

  const openProduct = useCallback((id: string) => {
    if (!getPhone(id)) return;
    setState((s) => ({ ...s, view: 'product', productId: id, highlight: null }));
  }, []);

  const applyFilters = useCallback((f: Filters) => {
    setState((s) => ({
      ...s,
      view: 'search',
      filters: { ...s.filters, ...f },
      highlight: null,
    }));
  }, []);

  const setQuery = useCallback((q: string) => {
    setState((s) => ({ ...s, view: 'search', query: q }));
  }, []);

  const toggleBrand = useCallback((brand: string) => {
    setState((s) => ({
      ...s,
      view: 'search',
      filters: { ...s.filters, brand: s.filters.brand === brand ? undefined : brand },
    }));
  }, []);

  const setMaxPrice = useCallback((max: number | undefined) => {
    setState((s) => ({ ...s, view: 'search', filters: { ...s.filters, maxPrice: max } }));
  }, []);

  const setCategory = useCallback((cat: string | undefined) => {
    setState((s) => ({
      ...s,
      view: 'search',
      filters: { ...s.filters, category: s.filters.category === cat ? undefined : cat },
    }));
  }, []);

  const setSort = useCallback((by: SortKey | undefined) => {
    setState((s) => ({ ...s, view: 'search', sortBy: by }));
  }, []);

  const clearFilters = useCallback(() => {
    setState((s) => ({ ...s, filters: {}, query: '', sortBy: undefined }));
  }, []);

  const highlightFeature = useCallback((productId: string, feature: string) => {
    setState((s) => ({
      ...s,
      view: 'product',
      productId,
      highlight: { productId, feature, nonce: (s.highlight?.nonce ?? 0) + 1 },
    }));
  }, []);

  const compare = useCallback((ids: string[]) => {
    const valid = ids.filter((id) => getPhone(id));
    if (valid.length < 2) return;
    setState((s) => ({ ...s, view: 'compare', compareIds: valid, highlight: null }));
  }, []);

  const addToCart = useCallback((id: string) => {
    if (!getPhone(id)) return;
    setState((s) => (s.cart.includes(id) ? s : { ...s, cart: [...s.cart, id] }));
  }, []);

  const toggleWishlist = useCallback((id: string) => {
    if (!getPhone(id)) return;
    setState((s) => ({
      ...s,
      wishlist: s.wishlist.includes(id) ? s.wishlist.filter((w) => w !== id) : [...s.wishlist, id],
    }));
  }, []);

  const addToWishlist = useCallback((id: string) => {
    if (!getPhone(id)) return;
    setState((s) => (s.wishlist.includes(id) ? s : { ...s, wishlist: [...s.wishlist, id] }));
  }, []);

  const openFaq = useCallback((topic?: string | null) => {
    setState((s) => ({ ...s, view: 'faq', faqTopic: topic ?? null, highlight: null }));
  }, []);

  const handleUiCommand = useCallback(
    (command: string, payload: Record<string, unknown>) => {
      const num = (v: unknown) => (typeof v === 'number' ? v : undefined);
      const str = (v: unknown) => (typeof v === 'string' && v ? v : undefined);
      switch (command) {
        case 'navigate_home':
          goHome();
          break;
        case 'show_search':
          showSearch({
            query: str(payload.query) ?? '',
            brand: str(payload.brand),
            maxPrice: num(payload.max_price),
            category: str(payload.category),
            sort: str(payload.sort_by) as SortKey | undefined,
          });
          break;
        case 'sort':
          setSort(str(payload.sort_by) as SortKey | undefined);
          break;
        case 'open_product':
          if (str(payload.product_id)) openProduct(str(payload.product_id)!);
          break;
        case 'apply_filters':
          applyFilters({
            brand: str(payload.brand),
            maxPrice: num(payload.max_price),
            minPrice: num(payload.min_price),
            category: str(payload.category),
          });
          break;
        case 'clear_filters':
          clearFilters();
          break;
        case 'highlight':
          if (str(payload.product_id) && str(payload.feature)) {
            highlightFeature(str(payload.product_id)!, str(payload.feature)!);
          }
          break;
        case 'compare':
          if (Array.isArray(payload.product_ids)) compare(payload.product_ids.map(String));
          break;
        case 'add_to_cart':
          if (str(payload.product_id)) addToCart(str(payload.product_id)!);
          break;
        case 'add_to_wishlist':
          if (str(payload.product_id)) addToWishlist(str(payload.product_id)!);
          break;
        case 'open_faq':
          openFaq(str(payload.topic) ?? null);
          break;
        default:
          // Unknown command — ignore quietly.
          break;
      }
    },
    [
      goHome,
      showSearch,
      setSort,
      openProduct,
      applyFilters,
      clearFilters,
      highlightFeature,
      compare,
      addToCart,
      addToWishlist,
      openFaq,
    ],
  );

  const results = useMemo<Phone[]>(() => {
    const f: CatalogFilters = { ...state.filters, query: state.query };
    return sortPhones(filterCatalog(f), state.sortBy);
  }, [state.filters, state.query, state.sortBy]);

  const cartPhones = useMemo<Phone[]>(
    () => state.cart.map((id) => getPhone(id)).filter((p): p is Phone => !!p),
    [state.cart],
  );

  const wishlistPhones = useMemo<Phone[]>(
    () => state.wishlist.map((id) => getPhone(id)).filter((p): p is Phone => !!p),
    [state.wishlist],
  );

  const store: MobileShopStore = {
    ...state,
    results,
    cartPhones,
    wishlistPhones,
    goHome,
    showSearch,
    openProduct,
    applyFilters,
    setQuery,
    toggleBrand,
    setMaxPrice,
    setCategory,
    setSort,
    clearFilters,
    highlightFeature,
    compare,
    addToCart,
    toggleWishlist,
    addToWishlist,
    openFaq,
    handleUiCommand,
  };

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useMobileShop(): MobileShopStore {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useMobileShop must be used within MobileShopProvider');
  return ctx;
}
