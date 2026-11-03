/**
 * The early shell, at `document_start` in the page's own world: in a call,
 * the widget is back the moment the next page shows, as the last page left it,
 * and the page load is a view transition under it. Off a call it does
 * nothing. The shared one from `@voqalize/stage/extension`.
 */

import { startShell } from "@voqalize/stage/extension";

import { SITE } from "./site";

startShell(SITE);
