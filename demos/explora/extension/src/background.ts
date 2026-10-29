/**
 * The extension's service worker: the shared one (it makes the holder, opens
 * and focuses tabs, keeps each tab's move for its next page, which may be on
 * the other host), plus one request of Explora's own, `alternate`: the
 * Spanish (or English) version of a www.explora.com page, read from its
 * `<head>`, for a tab on the booking site, which may not fetch
 * www.explora.com across origins, and for a page whose own fetch failed (a
 * script of the page may wrap it).
 */

import { startBackground } from "@voqalize/stage/extension";

import { fetchAlternates } from "./hreflang";
import { EXPLORA } from "./site";

startBackground(EXPLORA, {
  // Where a tab Javier opens may point: Explora's own hosts. Nothing else,
  // whatever the brain sends.
  openable: [/^https:\/\/([a-z0-9-]+\.)*explora\.com(\/|$)/i],
  justification: "Holds the voice call with Javier across Explora's page loads: the microphone, the WebRTC connection and his voice.",
  ops: {
    // `read`: the page named any translations at all (one that named none is
    // not remembered).
    async alternate(ask) {
      const url = String(ask.url ?? "");
      if (!/^https:\/\/(www\.)?explora\.com\//i.test(url)) return { url: null, read: false, error: "not a www.explora.com page" };
      try {
        const alts = await fetchAlternates(url);
        const read = Object.keys(alts).length > 0;
        return { url: alts[String(ask.lang ?? "en")] ?? null, read, ...(read ? {} : { error: "the page named no translations" }) };
      } catch (error) {
        return { url: null, read: false, error: error instanceof Error ? `${error.name}: ${error.message}` : String(error) };
      }
    },
  },
});
