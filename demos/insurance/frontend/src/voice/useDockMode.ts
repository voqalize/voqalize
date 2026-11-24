/**
 * Where the guide's idle dock and call tile sit, read from the page itself so
 * every overlay and primary action counts, whoever put it there (a click, or
 * one of the agent's moves).
 */
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

export const PHONE = "(max-width: 699px)";
export const isPhone = () => window.matchMedia(PHONE).matches;

/** The band at the bottom of the viewport the idle dock occupies, in px. */
const BAND = 84;

const visible = (r: DOMRect) => r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight;

/** The visible boxes of the page's primary actions (`data-dock-avoid`: Continue, Submit claim…). */
export function avoidRects(): DOMRect[] {
  return [...document.querySelectorAll<HTMLElement>("[data-dock-avoid]")].map((el) => el.getBoundingClientRect()).filter(visible);
}

/**
 * The visible boxes of whatever is open over the page (`data-overlay`: the
 * phone's menu, any drawer, sheet or dialog). The agent never sits on one: the
 * tile moves to a top corner clear of it, or the nearest free place.
 */
export function overlayRects(): DOMRect[] {
  return [...document.querySelectorAll<HTMLElement>("[data-overlay]")].map((el) => el.getBoundingClientRect()).filter(visible);
}

/**
 * The idle dock's state:
 *
 * - `side`: bottom right by default; bottom left when a primary action sits
 *   under the pill's place, so the pill never covers it.
 * - `hidden`: such an action (or an overlay) is under both places, so the pill
 *   steps aside.
 */
export function useDockMode() {
  const location = useLocation();
  const [side, setSide] = useState<"r" | "l">("r");
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let frame = 0;
    const check = () => {
      frame = 0;
      const dock = document.querySelector<HTMLElement>(".dock");
      const w = dock ? dock.getBoundingClientRect().width : 400;
      const top = window.innerHeight - BAND;
      const rects = [...avoidRects(), ...overlayRects()];
      const hits = (from: number, to: number) => rects.some((r) => r.bottom > top && r.right > from && r.left < to);
      const rightBlocked = hits(window.innerWidth - w - 24, window.innerWidth);
      const leftBlocked = hits(0, w + 24);
      setSide(rightBlocked && !leftBlocked ? "l" : "r");
      setHidden(rightBlocked && leftBlocked);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(check);
    };
    check();
    const t = window.setTimeout(check, 400);
    // A section opened by a move, or the menu, has no scroll event of its own.
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

  const classes = `${side === "l" ? " is-left" : ""}${hidden ? " is-hidden" : ""}`;
  return { side, hidden, classes };
}
