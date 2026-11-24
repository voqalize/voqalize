/**
 * Where the planner's idle bar and call tile sit, read from the page itself so
 * every overlay counts, whoever opened it (a tap, or one of her moves).
 * Paynora's widget, adapted to Wanderloom's pages.
 */
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

export const PHONE = "(max-width: 640px)";
export const isPhone = () => window.matchMedia(PHONE).matches;

/** The band at the bottom of the viewport the idle bar occupies, in px. */
const BAND = 84;

const visible = (el: Element) => {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/**
 * Which overlay is open over the page, if any. Overlays mark themselves
 * `data-overlay` (`bottom`: the trip summary sheet on a phone; `right`,
 * `left`, `center` for any drawer or dialog added later); one in the page but
 * not shown does not count.
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
 * The top corner the planner moves to while an overlay is open, so nothing of
 * it is hidden under her: top left away from a right-hand drawer, top right
 * otherwise. `null` with nothing open.
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

/** The trip summary's bar pinned to the bottom of a phone, when one shows: the bar and tile keep above it. */
export function bottomBar(): number {
  const el = document.querySelector(".summary-bar");
  const r = el?.getBoundingClientRect();
  return r && r.height && r.top < window.innerHeight && r.bottom >= window.innerHeight - 1 ? window.innerHeight - r.top : 0;
}

/**
 * The idle bar's state:
 *
 * - `side`: bottom right by default; bottom left when a primary action
 *   (`data-dock-avoid`: Review & pay, Pay…) sits under its place.
 * - `hidden`: such an action is under both places, so the bar steps aside.
 * - `raised`: an overlay is open, so the bar moves to a top corner above it.
 */
export function useDockMode() {
  const location = useLocation();
  const [side, setSide] = useState<"r" | "l">("r");
  const [hidden, setHidden] = useState(false);
  const [raised, setRaised] = useState<"tl" | "tr" | null>(null);
  const [lift, setLift] = useState(0);

  useEffect(() => {
    let frame = 0;
    const check = () => {
      frame = 0;
      const corner = raisedCorner();
      setRaised(corner);
      setLift(bottomBar());
      if (corner) {
        setHidden(false);
        return;
      }
      const dock = document.querySelector<HTMLElement>(".dock");
      const w = dock ? dock.getBoundingClientRect().width : 380;
      const bar = bottomBar();
      const top = window.innerHeight - BAND - bar;
      const hits = (from: number, to: number) => avoidRects().some((r) => r.bottom > top && r.top < window.innerHeight - bar && r.right > from && r.left < to);
      const rightBlocked = hits(window.innerWidth - w - 24, window.innerWidth);
      const leftBlocked = isPhone() ? true : hits(0, w + 24);
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
  return { side, hidden, raised, lift, classes };
}
