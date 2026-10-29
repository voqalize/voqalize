/**
 * The bridge between the page and the extension, in the extension's isolated
 * world on every PC Factory page: the shared one from
 * `@voqalize/stage/extension`, which carries the page's messages to the
 * holder and the service worker, and their answers back.
 */

import { startBridge } from "@voqalize/stage/extension";

startBridge();
