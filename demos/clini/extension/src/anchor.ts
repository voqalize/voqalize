/**
 * Runs at `document_start` on every Clini page, in the extension's isolated
 * world, so the elements the adapters match on are marked `translate="no"`
 * before Chrome's translator reaches them (see `anchors.ts`). The DOM is
 * shared with the page's world, where `content.ts` reads the marks and stamps.
 */

import { watchAnchors } from "./anchors";

watchAnchors();
