// The page test's bundle (`demos/tests/test_enveedo_page.py`): test/entry.ts,
// the real site adapter with its catalogue, as one IIFE at the path given.
//
//   node test/bundle-page.mjs <out.js>

import { build } from "esbuild";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { catalogue, cataloguePath } from "../catalogue.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const out = process.argv[2];
if (!out) throw new Error("usage: node test/bundle-page.mjs <out.js>");
await build({
  entryPoints: [join(here, "entry.ts")],
  bundle: true,
  format: "iife",
  target: "chrome120",
  plugins: [catalogue],
  outfile: out,
  logLevel: "error",
});
console.log(cataloguePath());
