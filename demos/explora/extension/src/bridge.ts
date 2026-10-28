/**
 * The bridge (isolated world, `document_start`): carries the page's messages
 * to the holder and the service worker, and back.
 */

import { startBridge } from "@voqalize/stage/extension";

startBridge();
