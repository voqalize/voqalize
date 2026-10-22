/**
 * The adapter as the end-to-end tests inject it: the anchors (`anchor.js` in
 * the extension) and the site adapter (in `content.js`), without the call or
 * the widget, plus the checkout guard for the tests to drive directly.
 */

import "../src/cannonhome-actions";

import { watchAnchors } from "../src/anchors";
import { forbiddenPath, go, intoCheckout, press } from "../src/page";

watchAnchors();
(window as unknown as Record<string, unknown>).__voqalizeTest = { press, go, intoCheckout, forbiddenPath };
