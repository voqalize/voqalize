/**
 * The early shell: in a call, the widget is back the moment the next page
 * shows, not once the page has parsed and the site's scripts have run.
 *
 * Runs at `document_start` in the page's own world, before any of the page's
 * scripts. Off a call it reads one `sessionStorage` key and does nothing
 * else. When the last page of this tab left a call on, it opts this page in
 * to the cross-document view transition, mounts the widget on `<html>` as the
 * last page left it (with the face's slot empty until the live face draws),
 * and leaves it for the content script, which adopts it. It defines one
 * property on `window` and adds two elements to `<html>`.
 */

import { readKept, transitions } from "./persist.js";
import { type SiteConfig, shellFlag } from "./site.js";
import { DEFAULT_TRANSITION_NAME, mountWidget } from "./widget.js";

export function startShell(site: SiteConfig): void {
  const kept = readKept(site.id);
  const flags = window as unknown as Record<string, unknown>;
  const flag = shellFlag(site);
  if (!kept || flags[flag] || !document.documentElement) return;
  transitions(true, site.widget.transitionName ?? DEFAULT_TRANSITION_NAME);
  const widget = mountWidget(site.widget);
  widget.setLanguage(kept.language);
  widget.paint(kept.status);
  widget.setMuted(kept.muted);
  if (kept.activity && kept.status === "live") widget.setActivity(kept.activity);
  widget.restore(kept);
  // The invite's still, for when the call ends on this page.
  if (kept.still) widget.setStill(kept.still);
  widget.veil();
  flags[flag] = { widget, kept };
}
