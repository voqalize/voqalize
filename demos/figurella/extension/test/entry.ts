/**
 * The page test's bundle (`demos/tests/test_figurella_page.py`): the real site
 * adapter, as the extension injects it, plus the pure helpers the test checks
 * on their own. Built by the test with this folder's esbuild; never shipped.
 */

import "../src/figurella-actions";

import { canonical, norm, phoneValue } from "../src/figurella-actions";

(window as unknown as Record<string, unknown>).__voqalizeTest = { canonical, norm, phoneValue };
