/**
 * Runs before SendPotion's own scripts (`document_start`, in the page's world)
 * to find the page's scroller.
 *
 * sendpotion.com does not scroll the window: its content sits in a
 * smooth-scrollbar container (`.pt-layout[data-scrollbar]`), translated by the
 * library, with GSAP's ScrollTrigger proxied onto it so the page's reveal
 * animations follow. `window.scrollTo` and `scrollIntoView` do nothing there,
 * and the library keeps its instances in a private `Map` keyed by element. So
 * this watches `Map.prototype.set` for the one entry whose value is a
 * scrollbar for its own key, and keeps it where the adapter can reach it. The
 * check is two property reads; every other `Map` is untouched.
 */

interface Scroller {
  containerEl: Element;
  offset: { x: number; y: number };
  limit: { x: number; y: number };
  scrollTo(x: number, y: number, duration?: number, options?: { callback?: () => void }): void;
}

declare global {
  interface Window {
    __voqalizeScrollers?: Set<Scroller>;
  }
}

(function () {
  if (window.__voqalizeScrollers) return;
  const found = new Set<Scroller>();
  window.__voqalizeScrollers = found;
  const set = Map.prototype.set;
  Map.prototype.set = function (this: Map<unknown, unknown>, key: unknown, value: unknown) {
    const v = value as Partial<Scroller> | null;
    if (v && typeof v === "object" && v.containerEl === key && typeof v.scrollTo === "function") {
      found.add(v as Scroller);
    }
    return set.call(this, key, value);
  } as typeof Map.prototype.set;
})();

export {};
