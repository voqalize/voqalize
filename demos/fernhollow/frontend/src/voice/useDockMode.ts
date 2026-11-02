import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

/** The band at the bottom of the viewport the dock occupies, in px. */
const BAND = 112;

/**
 * Where the dock sits right now.
 *
 * - `compact`: a small circle at the bottom right instead of the full pill —
 *   always on a phone, and on a wide screen once the shopper scrolls down
 *   (scrolling up brings the pill back). A live call never compacts.
 * - `hidden`: an element marked `data-dock-avoid` (Add to cart, checkout
 *   buttons) is inside the dock's band, so the dock steps aside for it.
 */
export function useDockMode(live: boolean) {
  const location = useLocation();
  const [compact, setCompact] = useState(false);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let lastY = window.scrollY;
    let frame = 0;
    const phone = window.matchMedia("(max-width: 699px)");
    const check = () => {
      frame = 0;
      const y = window.scrollY;
      if (phone.matches) setCompact(true);
      else if (y < 240) setCompact(false);
      else if (y > lastY + 4) setCompact(true);
      else if (y < lastY - 4) setCompact(false);
      lastY = y;
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
