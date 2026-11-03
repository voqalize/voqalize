/**
 * What one site is, for a Site Agent extension: the one file a new site adds
 * (`sites/<id>/site.ts`, `export default { … } satisfies SiteAgentSite`).
 *
 * Everything here is data (match patterns, colours, selectors, regular
 * expressions), so `build.mjs` reads the same file for the manifest that the
 * entry points are bundled against (`@site`). Only types are imported, and
 * Node strips them; nothing in a site file may import a value.
 *
 * What is NOT here, on purpose: the site's pages, regions, tools and
 * navigation. Those are the site's adapter, which the Site Agent's own
 * embed.config serves (the same one the paste-in snippet runs on), so the
 * extension shows the site exactly as the published Site Agent knows it.
 */

import type { SpotlightTheme } from "@voqalize/stage";
import type { WidgetTheme, WidgetWords } from "@voqalize/stage/extension";

export interface SiteAgentSite {
  /** Short and stable: storage keys, window flags and `dist/<id>/` ("wom"). */
  id: string;
  /** The site as a visitor names it, in the widget's words ("WOM"). */
  siteName: string;
  /** The site's main origin, no trailing slash (`https://www.wom.cl`): the
   *  first tab's page, and an Origin the site's key is allowed on. */
  origin: string;
  /** Every page the extension runs on (manifest match patterns). */
  matches: string[];
  /** Where a tab the agent opens may point (the service worker's guard):
   *  the site's own pages, never its login, account or payment flows. */
  openable: RegExp[];
  /** The manifest's `key`: an RSA public key (base64 DER, no PEM lines), so
   *  the unpacked extension has the same id from any folder. Never the
   *  private key. */
  manifestKey: string;
  /** The id that key gives (for the README and the key's allowed origins). */
  extensionId: string;
  /** The extension's description in chrome://extensions. */
  description: string;
  /** The widget's home corner, clear of the site's own floating buttons. */
  corner: "left" | "right";
  /** The last-resort top place keeps this far below the top: clear of the
   *  site's fixed header. */
  topClear: number;
  /** Selectors of the site's pinned bars, which a scroll keeps targets under. */
  fixed: string[];
  /** What the site pins over its corners, for the widget to keep clear of. */
  obstacles: { selector: string; fixedOnly?: boolean }[];
  /** The widget's colours and faces, read off the site. */
  theme: WidgetTheme;
  /** The ring around what the agent points at. */
  spotlight: SpotlightTheme;
  /** The grant page's look: text, button and font. */
  grantStyle: { ink: string; button: string; onButton: string; font: string };
  /** What the site opens over its pages on a visit (an offer pop-up), by its
   *  own close button: pressed when a call starts, so it covers nothing the
   *  agent rings. Never a consent or a choice of the visitor's. */
  dismissOnCall?: string[];
  /** Word overrides, by language, on top of the shared Javier words. */
  words?: Partial<Record<"es" | "en", Partial<WidgetWords>>>;
}
