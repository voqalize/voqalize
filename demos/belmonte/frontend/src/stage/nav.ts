/**
 * The router, for code outside React: a Stage performer navigates the app the
 * way a link does. `StageHost` (inside the router) hands its navigate here.
 */
import type { Page } from "../state/store";

type Go = (path: string) => void;
let go: Go | null = null;
export const setNavigate = (fn: Go | null) => {
  go = fn;
};
/** App paths, relative to the base: "/", "/dining", "/stay/check-in"… */
export const navigate = (path: string) => go?.(path);
export const currentPath = () => {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  const p = window.location.pathname.startsWith(base) ? window.location.pathname.slice(base.length) : window.location.pathname;
  return p.replace(/\/$/, "") || "/";
};

/** Each page's path. */
export const PAGE_PATH: Record<Page, string> = {
  home: "/",
  dining: "/dining",
  bar: "/bar",
  spa: "/spa",
  activities: "/activities",
  meetings: "/meetings",
  requests: "/requests",
  visitors: "/visitors",
  stay: "/stay",
  checkin: "/stay/check-in",
  checkout: "/stay/check-out",
  info: "/info",
};

/** The page a path is, as the brain hears it (`stay.page`). */
export function pageOfPath(pathname: string): Page {
  const p = pathname.replace(/^\/demos\/belmonte/, "").split("/").filter(Boolean);
  if (p[0] === "stay" && p[1] === "check-in") return "checkin";
  if (p[0] === "stay" && p[1] === "check-out") return "checkout";
  const known: Page[] = ["dining", "bar", "spa", "activities", "meetings", "requests", "visitors", "stay", "info"];
  return (known as string[]).includes(p[0] ?? "") ? (p[0] as Page) : "home";
}
