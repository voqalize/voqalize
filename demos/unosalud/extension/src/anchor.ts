/**
 * Runs at `document_start` on every Uno Salud page, in the extension's
 * isolated world, so the elements the adapters match on are marked
 * `translate="no"` before Chrome's translator reaches them, and a clinic
 * page's facts are read before it translates them (see `anchors.ts`). The DOM
 * is shared with the page's world, where `content.ts` reads the marks.
 */

import { watchAnchors } from "./anchors";

watchAnchors();
