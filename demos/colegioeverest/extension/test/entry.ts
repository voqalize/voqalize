/**
 * The page test's bundle (`demos/tests/test_colegioeverest_page.py`): the real site
 * adapter, as the extension injects it, plus the pure helpers the test checks
 * on their own. Built by the test with this folder's esbuild; never shipped.
 */

import "../src/colegioeverest-actions";

import { canonical, norm } from "../src/colegioeverest-actions";

(window as unknown as Record<string, unknown>).__voqalizeTest = { canonical, norm };
