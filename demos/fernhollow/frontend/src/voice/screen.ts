/**
 * What is on the shopper's screen, for "this one", "the one on the left" and
 * "the second one" (CONTRACT.md v2):
 *
 * - `visible_products{product_ids, layout}`: the product cards in view, in
 *   reading order, each with its row and column on screen. Recomputed after
 *   scrolling, resizing or a change of page, and sent only when it changed.
 * - `pointing{product_id, how}`: the card or product page under the pointer,
 *   a finger or keyboard focus, once it has stayed there 300 ms.
 */
import { useEffect } from "react";
import { emit, isLive, onSenderReady } from "./events";

const CARD = '.card[data-spot^="product:"], .inline-product[data-spot^="product:"]';
const idOf = (el: Element) => (el.getAttribute("data-spot") ?? "").slice("product:".length);

export interface Placed {
  product_id: string;
  row: number;
  col: number;
}

/** The cards in view, grouped into rows by their top edge, in reading order. */
export function screenLayout(root: ParentNode = document): Placed[] {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const header = document.querySelector(".site-header")?.getBoundingClientRect().bottom ?? 0;
  const seen = new Set<string>();
  const boxes = [...root.querySelectorAll(CARD)]
    .map((el) => ({ id: idOf(el), r: el.getBoundingClientRect() }))
    .filter(({ id, r }) => {
      if (!id || r.width === 0 || r.height === 0) return false;
      const visibleH = Math.min(r.bottom, vh) - Math.max(r.top, header);
      const visibleW = Math.min(r.right, vw) - Math.max(r.left, 0);
      return visibleH > r.height * 0.4 && visibleW > r.width * 0.6;
    })
    .sort((a, b) => a.r.top - b.r.top || a.r.left - b.r.left);
  const out: Placed[] = [];
  let row = 0;
  let rowTop = Number.NEGATIVE_INFINITY;
  let col = 0;
  for (const b of boxes) {
    if (Math.abs(b.r.top - rowTop) > 40) {
      row += 1;
      col = 0;
      rowTop = b.r.top;
    }
    col += 1;
    if (seen.has(b.id)) continue;
    seen.add(b.id);
    out.push({ product_id: b.id, row, col });
  }
  // Within a row, left to right.
  return out.sort((a, b) => a.row - b.row || a.col - b.col);
}

/** Report the visible layout while mounted; `key` is the route, to recompute on navigation. */
export function useScreenReport(key: string) {
  useEffect(() => {
    let last = "";
    let timer: ReturnType<typeof setTimeout> | undefined;
    const report = () => {
      const layout = screenLayout();
      const sig = layout.map((p) => `${p.product_id}@${p.row}.${p.col}`).join(",");
      if (!sig || sig === last) return;
      last = sig;
      emit("visible_products", { product_ids: layout.map((p) => p.product_id), layout });
    };
    const soon = () => {
      clearTimeout(timer);
      timer = setTimeout(report, 450);
    };
    const first = setTimeout(report, 700);
    // On connect the brain hears what is on screen at once, even if nothing moved since.
    const offReady = onSenderReady(() => {
      last = "";
      report();
    });
    const mo = new MutationObserver(soon);
    const main = document.getElementById("main");
    if (main) mo.observe(main, { childList: true, subtree: true });
    window.addEventListener("scroll", soon, { passive: true });
    window.addEventListener("resize", soon);
    // Horizontal rails scroll on their own.
    document.addEventListener("scroll", soon, { capture: true, passive: true });
    return () => {
      clearTimeout(timer);
      clearTimeout(first);
      offReady();
      mo.disconnect();
      window.removeEventListener("scroll", soon);
      window.removeEventListener("resize", soon);
      document.removeEventListener("scroll", soon, { capture: true });
    };
  }, [key]);
}

let pending: ReturnType<typeof setTimeout> | undefined;
let lastPoint = "";

/** The shopper is pointing at a product; reported once it holds for 300 ms. */
export function point(productId: string, how: "hover" | "focus" | "tap") {
  clearTimeout(pending);
  const send = () => {
    const sig = `${productId}:${how}`;
    if (sig === lastPoint) return;
    lastPoint = sig;
    emit("pointing", { product_id: productId, how });
  };
  // On a live call "this one" must already be known when the shopper says it:
  // a tap or a focus goes at once, a hover after a short settle.
  if (isLive() && how !== "hover") send();
  else pending = setTimeout(send, isLive() ? 120 : 300);
}

/** The pointer left before 300 ms: nothing is reported. */
export function unpoint() {
  clearTimeout(pending);
  lastPoint = "";
}

/** Handlers for an element that stands for one product. */
export function pointHandlers(productId: string) {
  return {
    onPointerEnter: (e: React.PointerEvent) => {
      if (e.pointerType === "mouse") point(productId, "hover");
    },
    onPointerDown: (e: React.PointerEvent) => {
      if (e.pointerType !== "mouse") point(productId, "tap");
    },
    onPointerLeave: (e: React.PointerEvent) => {
      if (e.pointerType === "mouse") unpoint();
    },
    onFocus: () => point(productId, "focus"),
  };
}
