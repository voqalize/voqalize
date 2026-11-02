import { useEffect } from "react";
import { emit } from "../voice/events";

const STORE = "Fernhollow";

/** Sets the document title; `null` is the home page. */
export function useTitle(title: string | null) {
  useEffect(() => {
    document.title = title ? `${title} — ${STORE}` : `${STORE} — furniture and homeware for calm rooms`;
  }, [title]);
}

/** Reports the products a listing is showing, once it settles. */
export function useVisibleProducts(ids: string[]) {
  const key = ids.slice(0, 24).join(",");
  useEffect(() => {
    if (!key) return;
    const t = window.setTimeout(() => emit("visible_products", { product_ids: key.split(",") }), 600);
    return () => window.clearTimeout(t);
  }, [key]);
}
