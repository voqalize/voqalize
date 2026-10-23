/**
 * The page test's bundle (`demos/tests/test_saintgeorge_page.py`): the real
 * site adapter, as the extension injects it, plus the pure helpers the test
 * checks on their own — the calendar's parser and the admission page's fee
 * reader. Built by the test with this folder's esbuild; never shipped.
 */

import "../src/saintgeorge-actions";

import { parseIcs, todayIn, upcoming } from "../src/ical";
import { readFees } from "../src/saintgeorge-actions";

(window as unknown as Record<string, unknown>).__voqalizeTest = { parseIcs, upcoming, todayIn, readFees };
