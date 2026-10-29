/**
 * The early shell (MAIN world, `document_start`): in a call, the widget is
 * back the moment the next Explora page shows, as the last page left it, and
 * the load is a view transition under it. Off a call it does nothing.
 */

import { startShell } from "@voqalize/stage/extension";

import { EXPLORA } from "./site";

startShell(EXPLORA);
