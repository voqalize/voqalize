/**
 * The router, for code outside React: a Stage performer navigates the app the
 * way a link does. `Navigator` (inside the router) hands its navigate here.
 */
type Go = (path: string) => void;
let go: Go | null = null;
export const setNavigate = (fn: Go | null) => {
  go = fn;
};
/** App paths, relative to the base: "/", "/plan", "/checkout", "/booked". */
export const navigate = (path: string) => go?.(path);
export const currentPath = () => {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  const p = window.location.pathname.startsWith(base) ? window.location.pathname.slice(base.length) : window.location.pathname;
  return p.replace(/\/$/, "") || "/";
};
