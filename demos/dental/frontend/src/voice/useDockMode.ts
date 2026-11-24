/**
 * Where Meera's idle dock and call tile sit, read from the page itself so every
 * overlay counts, whoever opened it (a tap, or one of her moves). Paynora's
 * widget, adapted to the clinic's header-only layout.
 */
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

export const PHONE = "(max-width: 640px)";
export const isPhone = () => window.matchMedia(PHONE).matches;

/** The band at the bottom of the viewport the idle dock occupies, in px. */
const BAND = 84;
/** How far in from the right edge the agent sits (the dock, the tile at rest). */
const AGENT_W = 460;

/**
 * Which overlay is open over the page, if any. Overlays mark themselves
 * `data-overlay`; the clinic's one is the callback card (`bottom`), which
 * counts only where it reaches the agent's side of the screen (a phone, where
 * it is the full width). On a desktop it sits bottom left and the agent stays.
 */
export function openOverlay(): "right" | "left" | "center" | "bottom" | null {
  const marks = [...document.querySelectorAll<HTMLElement>("[data-overlay]")].filter((el) => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    return el.dataset.overlay !== "bottom" || r.right > window.innerWidth - AGENT_W;
  });
  const kinds = marks.map((el) => el.dataset.overlay);
  if (kinds.includes("right")) return "right";
  if (kinds.includes("left")) return "left";
  if (kinds.includes("center")) return "center";
  if (kinds.includes("bottom")) return "bottom";
  return null;
}

/**
 * The top corner the agent moves to while an overlay is open, so nothing of it
 * is hidden under her: top left away from a right-hand drawer, top right
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

/**
 * The idle dock's state:
 *
 * - `side`: bottom right by default; bottom left when a primary action
 *   (`data-dock-avoid`: Book, Confirm, Send code…) sits under the pill's
 *   place, so the pill never covers it.
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
      const top = window.innerHeight - BAND;
      const hits = (from: number, to: number) => avoidRects().some((r) => r.bottom > top && r.right > from && r.left < to);
      const rightBlocked = hits(window.innerWidth - w - 24, window.innerWidth);
      // A phone's pill is the full width: there is no other side to go to.
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
  return { side, hidden, raised, classes };
}
