/**
 * The page test's bundle (`demos/tests/test_enveedo_page.py`, built by
 * `test/bundle-page.mjs`): the real site adapter, as the extension injects it,
 * with its catalogue, plus the pure helpers the test checks on their own.
 * Never shipped.
 */

import "../src/enveedo-actions";

import { canonical, norm } from "../src/enveedo-actions";
import { twinPath, twinUrl } from "../src/site-language";

(window as unknown as Record<string, unknown>).__voqalizeTest = { canonical, norm, twinPath, twinUrl };
