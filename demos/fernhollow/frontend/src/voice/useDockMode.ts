import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useCart } from "../state/cart";
import { useShortlist } from "../state/shortlist";

/** The band at the bottom of the viewport the dock occupies, in px. */
const BAND = 112;
const PHONE = "(max-width: 699px)";

/**
 * Which drawer or sheet is open over the page, if any: a side drawer (the
 * cart, a policy) or the saved-pieces sheet from the bottom. Read from the
 * page itself, so every overlay counts, whoever opened it.
 */
export function openOverlay(): "right" | "left" | "bottom" | null {
  const root = document.querySelector(".drawer-root");
  if (!root) return null;
  if (root.querySelector(".tray")) return "bottom";
  if (root.querySelector(".drawer-left")) return "left";
  return "right";
}

/**
 * The top corner the agent moves to while an overlay is open (owner, round 1,
 * F2/X2: the cart drawer and the saved sheet covered her): away from a side
 * drawer, and top right above a bottom sheet. `null` with nothing open.
 */
export function raisedCorner(): "tl" | "tr" | null {
  const o = openOverlay();
  if (o === null) return null;
  return o === "right" ? "tl" : "tr";
}

/**
 * Where the dock sits right now.
 *
 * - `compact`: a small circle at the bottom right instead of the full pill,
 *   on a phone only. On a wide screen the pill stays bottom centre however
 *   the shopper scrolls. A live call never compacts.
 * - `hidden`: an element marked `data-dock-avoid` (Add to cart, checkout
 *   buttons) is inside the dock's band, so the dock steps aside for it.
 * - `raised`: a drawer or sheet is open, so the dock moves to a top corner,
 *   above the overlay, instead of being covered by it.
 */
export function useDockMode(live: boolean) {
  const location = useLocation();
  // From the first paint: starting wide and compacting in an effect moved the
  // dock across a phone's screen on every load, and the face chased it.
  const [compact, setCompact] = useState(() => window.matchMedia(PHONE).matches);
  const [hidden, setHidden] = useState(false);
  const [raised, setRaised] = useState<"tl" | "tr" | null>(null);
  const cartOpen = useCart((s) => s.open);
  const trayOpen = useShortlist((s) => s.open);

  useEffect(() => {
    let frame = 0;
    const phone = window.matchMedia(PHONE);
    const check = () => {
      frame = 0;
      setCompact(phone.matches);
      const corner = raisedCorner();
      setRaised(corner);
      const top = window.innerHeight - BAND;
      const blocked =
        !corner &&
        [...document.querySelectorAll<HTMLElement>("[data-dock-avoid]")].some((el) => {
          const r = el.getBoundingClientRect();
          return r.width > 0 && r.bottom > top && r.top < window.innerHeight;
        });
      setHidden(blocked);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(check);
    };
    check();
    const t = window.setTimeout(check, 400);
    // An overlay opened by a move (the policy panel) has no event of its own.
    const poll = window.setInterval(schedule, 500);
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    phone.addEventListener("change", schedule);
    return () => {
      window.clearTimeout(t);
      window.clearInterval(poll);
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      phone.removeEventListener("change", schedule);
    };
  }, [location.pathname, cartOpen, trayOpen]);

  const classes = `${compact && !live ? " is-compact" : ""}${hidden ? " is-hidden" : ""}${raised ? ` is-raised is-raised-${raised}` : ""}`;
  return { compact: compact && !live, hidden, raised, classes };
}
