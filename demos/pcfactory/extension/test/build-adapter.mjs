// Bundles test/entry.ts (the site adapter and the anchors, no call) into
// test/.build/adapter.js, which the end-to-end tests inject into each page.

import { build } from "esbuild";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
await build({
  entryPoints: [join(here, "entry.ts")],
  bundle: true,
  format: "iife",
  target: "chrome120",
  outfile: join(here, ".build", "adapter.js"),
  logLevel: "warning",
});
