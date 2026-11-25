/**
 * What the shopper (or the agent) changed, told as the spec's state events
 * (CONTRACT.md, "Page → brain"): the page on every route change, the search
 * (debounced, once the catalogue is in), the size picked and the Find my size
 * panel, the bag, the wishlist and the checkout's completeness (booleans
 * only). Call once, in the shell. The service pages (orders, returns, gifts,
 * kiosk) send their own events from their pages.
 */
import { useEffect } from "react";
import { create } from "zustand";
import { getProduct, loadCatalog, search, summarise } from "../data/catalog";
import { bagTotals } from "../data/shop";
import { useStore } from "../state/store";
import { announce, sendEvent } from "./host";

/** Whether each checkout section is complete; the checkout page sets it, nothing it typed. */
export const useCheckoutFlags = create<{ contact: boolean; address: boolean; payment: boolean }>(() => ({ contact: false, address: false, payment: false }));

const TITLES: Record<string, string> = {
  shop: "Shop",
  compare: "Compare",
  wishlist: "Wishlist",
  bag: "Bag",
  checkout: "Checkout",
  about: "About Fashio",
  gifts: "Gift finder",
  orders: "Orders",
  returns: "Returns",
  kiosk: "Store kiosk",
};

export function pageOf(path: string, query: string): { page: string; product_id?: string; order_id?: string; title?: string } {
  const product = /^\/p\/(\d+)/.exec(path)?.[1];
  if (product) return { page: "product", product_id: product, title: getProduct(product)?.name };
  if (path === "/") return { page: "home", title: "Home" };
  const name = path.slice(1).split("/")[0] ?? "";
  const order = new URLSearchParams(query).get("order") ?? undefined;
  if (!TITLES[name]) return { page: "not_found", title: "Page not found" };
  const title = name === "shop" && path !== "/shop" ? `Shop: ${path.slice(6).replace("/", ", ")}` : TITLES[name];
  return { page: name, title, ...(order && (name === "orders" || name === "returns") ? { order_id: order } : {}) };
}

export const bagLines = () => useStore.getState().bag.map((l) => `${l.product_id}|${l.size}|${l.qty}|${l.gift ? 1 : 0}`);

export function useStageReport(path: string, query: string): void {
  useEffect(() => {
    let live = true;
    const send = () => {
      if (!live) return;
      announce();
      sendEvent("screen.viewed", { path: path + query, ...pageOf(path, query) });
    };
    // A product page's title needs the catalogue.
    if (/^\/p\/\d+/.test(path)) void loadCatalog().then(send, send);
    else send();
    return () => {
      live = false;
    };
  }, [path, query]);

  useEffect(() => {
    let shopTimer = 0;
    const fitTimers = new Map<number, number>();
    const sendShop = () => {
      window.clearTimeout(shopTimer);
      // A move ticks several filters in a row: one event for the lot, 250 ms
      // after the last (still inside the agent's window, so `by` stays right).
      shopTimer = window.setTimeout(() => {
        void loadCatalog().then(() => {
          const f = useStore.getState().filters;
          const results = search(f);
          sendEvent("shop.changed", {
            summary: summarise(f),
            count: results.length,
            dept: f.dept,
            types: f.types,
            brands: f.brands,
            colours: f.colours,
            sizes: f.sizes,
            price_min: f.price_min,
            price_max: f.price_max,
            discount_min: f.discount_min,
            usage: f.usage,
            seasons: f.seasons,
            query: f.query,
            sort: f.sort,
            ids: results.slice(0, 12).map((p) => String(p.id)),
          });
        });
      }, 250);
    };
    const unsub = useStore.subscribe((s, prev) => {
      if (s.filters !== prev.filters) sendShop();
      if (s.size !== prev.size) {
        for (const id of Object.keys(s.size)) {
          const n = Number(id);
          if (s.size[n] !== prev.size[n]) sendEvent("product.size_picked", { product_id: id, size: s.size[n] });
        }
      }
      if (s.fit !== prev.fit) {
        for (const id of Object.keys(s.fit)) {
          const n = Number(id);
          const a = s.fit[n];
          const b = prev.fit[n];
          if (!a || (b && a.height_cm === b.height_cm && a.usual_size === b.usual_size && a.fit === b.fit)) continue;
          window.clearTimeout(fitTimers.get(n));
          fitTimers.set(
            n,
            window.setTimeout(() => {
              const now = useStore.getState().fit[n];
              sendEvent("fit.changed", { product_id: id, height_cm: now?.height_cm, usual_size: now?.usual_size, fit: now?.fit });
            }, 400),
          );
        }
      }
      if (s.bag !== prev.bag) {
        void loadCatalog().then(() => {
          const t = bagTotals(useStore.getState().bag);
          sendEvent("bag.changed", { count: t.count, total: t.total, lines: bagLines() });
        });
      }
      if (s.wishlist !== prev.wishlist) sendEvent("wishlist.changed", { count: s.wishlist.length, ids: s.wishlist.map(String) });
    });
    const unsubCheckout = useCheckoutFlags.subscribe((s, prev) => {
      if (s.contact !== prev.contact || s.address !== prev.address || s.payment !== prev.payment) sendEvent("checkout.changed", { contact: s.contact, address: s.address, payment: s.payment });
    });
    return () => {
      window.clearTimeout(shopTimer);
      for (const t of fitTimers.values()) window.clearTimeout(t);
      unsub();
      unsubCheckout();
    };
  }, []);
}
