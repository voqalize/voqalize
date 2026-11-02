import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

/** The band at the bottom of the viewport the dock occupies, in px. */
const BAND = 112;

/**
 * Where the dock sits right now.
 *
 * - `compact`: a small circle at the bottom right instead of the full pill,
 *   on a phone only. On a wide screen the pill stays bottom centre however
 *   the shopper scrolls. A live call never compacts.
 * - `hidden`: an element marked `data-dock-avoid` (Add to cart, checkout
 *   buttons) is inside the dock's band, so the dock steps aside for it.
 */
export function useDockMode(live: boolean) {
  const location = useLocation();
  const [compact, setCompact] = useState(false);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let frame = 0;
    const phone = window.matchMedia("(max-width: 699px)");
    const check = () => {
      frame = 0;
      setCompact(phone.matches);
      const top = window.innerHeight - BAND;
      const blocked = [...document.querySelectorAll<HTMLElement>("[data-dock-avoid]")].some((el) => {
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
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    phone.addEventListener("change", schedule);
    return () => {
      window.clearTimeout(t);
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      phone.removeEventListener("change", schedule);
    };
  }, [location.pathname]);

  const classes = `${compact && !live ? " is-compact" : ""}${hidden ? " is-hidden" : ""}`;
  return { compact: compact && !live, hidden, classes };
}
