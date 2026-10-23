/**
 * The small rules the adapter and the Calendly frame share, kept free of the
 * DOM so `test/site.test.mjs` can run them in Node.
 *
 *   - sendpotion.com and www.sendpotion.com are one site. Both hosts serve
 *     every page, and the extension loads on both. On prod (2026-10-22) every
 *     page move on www failed: each path was resolved against the bare host
 *     and then refused as "not on this tab's site".
 *   - Calendly writes a slot's `data-start-time` as "3:00pm" or as "15:00",
 *     by the visitor's locale; Javier says either. Both sides are read the same
 *     way, as "3:00pm".
 */

/** A host as the site knows it: lower case, without `www.`. */
export const siteHost = (host: string): string => host.toLowerCase().replace(/^www\./, "");

/**
 * `path` on the tab at `here`, on that tab's own host, so the site's router
 * takes the link rather than a full page load to the other host; `null` when
 * it is on another site.
 */
export function onThisTab(path: string, here: string): URL | null {
  const tab = new URL(here);
  const target = new URL(path, tab.origin);
  if (siteHost(target.host) !== siteHost(tab.host)) return null;
  return new URL(`${target.pathname}${target.search}${target.hash}`, tab.origin);
}

const fold = (s: string | null | undefined) =>
  (s ?? "").replace(/\s+/g, " ").trim().toLowerCase().replace(/[.,]/g, "");

/** "3pm", "3:00 pm", "15:00", "3:00 p.m." → Calendly's "3:00pm". */
export function normTime(said: string | null | undefined): string {
  const flat = fold(said).replace(/\s+/g, "");
  const m = flat.match(/^(\d{1,2})(?::(\d{2}))?(am|pm)?$/);
  if (!m) return flat;
  let h = Number(m[1]);
  const min = m[2] ?? "00";
  let ap = m[3];
  if (!ap) {
    ap = h >= 12 ? "pm" : "am";
    if (h > 12) h -= 12;
  }
  return `${h === 0 ? 12 : h}:${min}${ap}`;
}
