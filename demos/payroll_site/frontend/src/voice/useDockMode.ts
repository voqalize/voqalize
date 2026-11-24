/**
 * Where the agent's dock and face go while the page changes under them.
 *
 * Paynora has two things that open over the page:
 *
 * - the lead card ("Your brief"): a side panel on the right on a wide screen,
 *   a bottom sheet on a phone;
 * - the phone menu, dropping down under the header.
 *
 * A bottom sheet would cover the dock and the face tile, so while one is open
 * the agent moves to a top corner above it (`raisedCorner`) and the sheet is
 * shortened so none of its rows sit under the agent (voice.css). The side
 * panel covers neither on a wide screen: the dock re-centres in the room left
 * of it and the tile keeps off it (`tileBlockers`). The phone menu lives at
 * the top, so the tile keeps out of the top corners while it is open.
 */
import { shownNow } from "../stage/view";
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useSite } from "../state/store";

/** The band at the bottom of the viewport the dock pill occupies, in px. */
const BAND = 96;
export const PHONE = "(max-width: 700px)";
export const isPhone = () => window.matchMedia(PHONE).matches;

/** Which overlay is open over the page, read from the page itself. */
export function openOverlay(): "sheet" | "panel" | "menu" | null {
  if (document.querySelector(".lead-card")) return isPhone() ? "sheet" : "panel";
  if (document.querySelector(".site-header.is-open")) return "menu";
  return null;
}

/**
 * The top corner the agent moves to while a bottom sheet is open (owner,
 * round 1, X2), or `null`. Top left: the sheet's own close sits top right.
 */
export function raisedCorner(): "tl" | "tr" | null {
  return openOverlay() === "sheet" ? "tl" : null;
}

/** What the floating tile must not cover: primary buttons, an open side
 *  panel and the brief tab, the phone menu while it is down, and what the
 *  agent is showing right now (`shownNow`, stage/view.ts). */
export function tileBlockers(): DOMRect[] {
  const sel = ["[data-dock-avoid]", "[data-tile-avoid]"];
  if (openOverlay() === "menu") sel.push(".site-header.is-open .header-nav");
  return [...document.querySelectorAll<HTMLElement>(sel.join(","))]
    .map((el) => el.getBoundingClientRect())
    .concat(shownNow())
    .filter((r) => r.width > 0 && r.bottom > 0 && r.top < window.innerHeight);
}

/**
 * Where the dock pill sits right now.
 *
 * - `hidden`: an element marked `data-dock-avoid` (Confirm booking, a hero
 *   button) is under the pill, so the pill steps aside for it.
 * - `raised`: a bottom sheet is open, so the pill moves to a top corner.
 */
export function useDockMode(live: boolean) {
  const location = useLocation();
  const leadOpen = useSite((s) => s.leadOpen);
  const [hidden, setHidden] = useState(false);
  const [raised, setRaised] = useState<"tl" | "tr" | null>(null);

  useEffect(() => {
    let frame = 0;
    const check = () => {
      frame = 0;
      const corner = raisedCorner();
      setRaised(corner);
      const dock = document.querySelector<HTMLElement>(".dock")?.getBoundingClientRect();
      const top = window.innerHeight - BAND;
      const blocked =
        !corner &&
        !live &&
        !!dock &&
        [...document.querySelectorAll<HTMLElement>("[data-dock-avoid]")].some((el) => {
          const r = el.getBoundingClientRect();
          // Mostly on screen and in the band: a button just peeking in at the
          // bottom edge (Confirm booking on load) does not hide the agent.
          const shown = Math.min(r.bottom, window.innerHeight) - Math.max(r.top, top);
          return r.width > 0 && shown >= r.height * 0.5 && r.left < dock.right && r.right > dock.left;
        });
      setHidden(blocked);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(check);
    };
    check();
    const t = window.setTimeout(check, 400);
    // The brief opened by a move, or the menu, has no event of its own here.
    const poll = window.setInterval(schedule, 500);
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.clearTimeout(t);
      window.clearInterval(poll);
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, [location.pathname, leadOpen, live]);

  const classes = `${hidden ? " is-hidden" : ""}${raised ? ` is-raised is-raised-${raised}` : ""}`;
  return { hidden, raised, classes };
}
