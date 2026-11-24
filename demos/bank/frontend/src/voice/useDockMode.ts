/**
 * Where the assistant's idle dock and call tile sit, read from the page itself
 * so every overlay counts, whoever opened it (a tap, or one of the agent's
 * moves). Paynora's widget, adapted to the bank's pages.
 */
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

export const PHONE = "(max-width: 640px)";
export const isPhone = () => window.matchMedia(PHONE).matches;

/** The band at the bottom of the viewport the idle dock occupies, in px. */
const BAND = 84;

const visible = (el: Element) => {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/**
 * Which overlay is open over the page, if any. Overlays mark themselves
 * `data-overlay` (`center`: the confirmation sheet; `bottom`: a transaction's
 * detail sheet on a phone; `left`: the app's phone menu); one that is in the
 * page but not shown (the detail panel's scrim on a desktop) does not count.
 */
export function openOverlay(): "right" | "left" | "center" | "bottom" | null {
  const marks = [...document.querySelectorAll<HTMLElement>("[data-overlay]")].filter(visible).map((el) => el.dataset.overlay);
  if (marks.includes("right")) return "right";
  if (marks.includes("left")) return "left";
  if (marks.includes("center")) return "center";
  if (marks.includes("bottom")) return "bottom";
  return null;
}

/**
 * The top corner the agent moves to while an overlay is open, so nothing of it
 * is hidden under the agent: top left away from a right-hand drawer, top right
 * otherwise (over the menu, a centred dialog, or above a bottom sheet). `null`
 * with nothing open.
 */
export function raisedCorner(): "tl" | "tr" | null {
  const o = openOverlay();
  if (o === null) return null;
  return o === "right" ? "tl" : "tr";
}

/** The visible boxes of the page's primary actions (`data-dock-avoid`). */
export function avoidRects(): DOMRect[] {
  return [...document.querySelectorAll<HTMLElement>("[data-dock-avoid]")]
    .map((el) => el.getBoundingClientRect())
    .filter((r) => r.width > 0 && r.bottom > 0 && r.top < window.innerHeight);
}

/** The signed-in app's bottom tab bar, when one is showing: the dock and tile keep above it. */
export function tabBar(): number {
  const r = document.querySelector(".ax-tabs")?.getBoundingClientRect();
  return r && r.height && r.top < window.innerHeight ? window.innerHeight - r.top : 0;
}

/**
 * The idle dock's state:
 *
 * - `side`: bottom right by default; bottom left (just past the app's side
 *   navigation) when a primary action (`data-dock-avoid`: Submit, Continue…)
 *   sits under the pill's place, so the pill never covers it.
 * - `hidden`: such an action is under both places, so the pill steps aside.
 * - `raised`: an overlay is open, so the pill moves to a top corner above it.
 */
export function useDockMode() {
  const location = useLocation();
  const [side, setSide] = useState<"r" | "l">("r");
  const [hidden, setHidden] = useState(false);
  const [raised, setRaised] = useState<"tl" | "tr" | null>(null);

  useEffect(() => {
    let frame = 0;
    const check = () => {
      frame = 0;
      const corner = raisedCorner();
      setRaised(corner);
      if (corner) {
        setHidden(false);
        return;
      }
      const dock = document.querySelector<HTMLElement>(".dock");
      const w = dock ? dock.getBoundingClientRect().width : 380;
      const top = window.innerHeight - BAND - tabBar();
      const sideNav = document.querySelector(".ax-side")?.getBoundingClientRect();
      const leftEdge = sideNav && sideNav.width && sideNav.left >= 0 && sideNav.width < window.innerWidth / 2 ? sideNav.right : 0;
      const hits = (from: number, to: number) => avoidRects().some((r) => r.bottom > top && r.top < window.innerHeight - tabBar() && r.right > from && r.left < to);
      const rightBlocked = hits(window.innerWidth - w - 24, window.innerWidth);
      const leftBlocked = isPhone() ? true : hits(leftEdge, leftEdge + w + 24);
      setSide(rightBlocked && !leftBlocked ? "l" : "r");
      setHidden(rightBlocked && leftBlocked);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(check);
    };
    check();
    const t = window.setTimeout(check, 400);
    // An overlay opened by a move has no event of its own.
    const poll = window.setInterval(schedule, 400);
    window.addEventListener("scroll", schedule, { passive: true, capture: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.clearTimeout(t);
      window.clearInterval(poll);
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule, { capture: true });
      window.removeEventListener("resize", schedule);
    };
  }, [location.pathname]);

  const classes = `${side === "l" ? " is-left" : ""}${hidden ? " is-hidden" : ""}${raised ? ` is-raised is-raised-${raised}` : ""}`;
  return { side, hidden, raised, classes };
}
