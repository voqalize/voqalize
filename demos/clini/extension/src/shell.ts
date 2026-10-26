/**
 * The early shell: in a call, the widget is back the moment the next page
 * shows, not once the page has loaded and its scripts have run.
 *
 * Runs at `document_start` in the page's own world, before any of the page's
 * own scripts, on every Clini page. Off a call it does nothing at all.
 * When the last page of this tab left a call on (`persist.ts`, in the tab's
 * `sessionStorage`), it:
 *
 *   - opts this page in to the cross-document view transition, so the page
 *     that is leaving fades into this one under a widget that stays put;
 *   - mounts the widget on <html> at once, as the last page left it: live (or
 *     connecting), where the visitor put it, minimised or not, the status line,
 *     the language, muted or not, and a still of his face where his face
 *     goes: his mouth strip, whose lips move with his voice (`mouth.ts`), or,
 *     should it not load, the last frame the avatar drew there, else the
 *     character's still;
 *   - leaves it for `content.ts` (at `document_idle`), which adopts it instead
 *     of mounting another, asks the holder for the call's state as before, and
 *     hands the still over to the live face once the avatar has drawn it.
 *
 * It defines one property on `window` and adds two elements to <html>; it
 * touches nothing of the page's.
 */

import { MOUTH_STRIP, voiceMouth } from "./mouth";
import { readFace, readKept, transitions } from "./persist";
import { mountWidget } from "./widget";

/** Where `content.ts` finds what this script mounted. */
const SHELL = "__voqalizeCliniJavierShell";

const kept = readKept();
const flags = window as unknown as Record<string, unknown>;
if (kept && !flags[SHELL] && document.documentElement) {
  transitions(true);
  const widget = mountWidget();
  widget.setLanguage(kept.language);
  widget.paint(kept.status);
  widget.setMuted(kept.muted);
  if (kept.activity && kept.status === "live") widget.setActivity(kept.activity);
  widget.restore(kept);
  if (kept.still) widget.setStill(kept.still);
  widget.setPoster(readFace() ?? kept.still);
  // His mouth strip in its place, its lips moving with his voice until the
  // live face draws (`mouth.ts`).
  voiceMouth(widget, Boolean(MOUTH_STRIP) && kept.strip === MOUTH_STRIP);
  flags[SHELL] = { widget, kept };
}
