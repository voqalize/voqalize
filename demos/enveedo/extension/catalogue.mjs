// The esbuild plugin that bundles the brain's catalogue of places,
// ../backend/knowledge/L3/anchors.json, into the site adapter as
// `virtual:enveedo-anchors`; `src/anchors.stub.json` (the same shape, a few
// pages) while the brain has not written it. Shared by build.mjs and the page
// test's bundle (test/bundle-page.mjs).

import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const CATALOGUE = join(here, "..", "backend", "knowledge", "L3", "anchors.json");
export const STUB = join(here, "src", "anchors.stub.json");

export const cataloguePath = () => (existsSync(CATALOGUE) ? CATALOGUE : STUB);

export const catalogue = {
  name: "voqalize-enveedo-anchors",
  setup(b) {
    b.onResolve({ filter: /^virtual:enveedo-anchors$/ }, () => ({ path: cataloguePath() }));
  },
};
