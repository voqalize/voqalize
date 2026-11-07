// What each browser entry costs a page, minified and gzipped, against a
// budget. Exits 1 when anything is over.
//
//   pnpm size              # check every entry and lazy chunk against its budget
//   pnpm size --propose    # print the budgets the rule below gives for today's sizes
//
// Each entry is built as a page's bundler would build it: minified, split,
// the optional avatar peer left out. "Up front" is the entry and every chunk
// it imports statically, which is what loads before anything happens. A
// dynamic import is a lazy chunk: it loads only when it is needed and is not
// counted up front.
//
// The lazy chunks are measured from the widget's build (the
// `defineElements()` entry): the session (on the first call), and the
// elements that load on first use (`LAZY_ELEMENTS` in src/elements/lazy.ts).
// A lazy chunk's size is its own code plus any shared chunk it pulls in that
// is not already up front.
//
// How a budget is set: today's gzipped size, plus 10% headroom, rounded up
// to the next 256 B. Ten percent lets an ordinary change land without
// touching this file; anything bigger has to be argued for here, by raising
// the number with the reason beside it. `--propose` prints what the rule
// gives; the budgets below were set from it on 2026-11-07, with the measured
// size beside each.

import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { relative } from "node:path";
import { build } from "esbuild";

const root = fileURLToPath(new URL("..", import.meta.url));
const propose = process.argv.includes("--propose");

/** Entries, each with its up-front budget in gzipped bytes. */
const ENTRIES = [
  // The version only.
  { name: "@voqalize/web", file: "src/index.ts", budget: 256 }, // measured 56 B
  // The closed button: the first paint.
  { name: "@voqalize/web/launcher", file: "src/launcher.ts", budget: 2048 }, // measured 1826 B
  // What a page that calls `defineElements()` loads before a call: Lit, the
  // widget and the elements every call shows.
  { name: "@voqalize/web/widgets (defineElements)", file: "scripts/size-elements.ts", budget: 33536 }, // measured 30418 B
  // Everything the entry exports, imported at once (no tree-shaking).
  { name: "@voqalize/web/widgets (whole surface)", file: "src/widgets.ts", budget: 39936 }, // measured 36107 B
  // The React wrappers and hooks, React itself left to the page.
  { name: "@voqalize/web/react", file: "src/react.ts", budget: 34560 }, // measured 31413 B
];

/** Lazy chunks, by the source module that starts them, with their budgets. */
const LAZY = [
  // pipecat, the transport and the session: on the first call.
  { name: "session (first call)", module: "src/session/adapter.ts", budget: 139264 }, // measured 126444 B
  { name: "vql-devices", module: "src/elements/devices.ts", budget: 1792 }, // measured 1488 B
  { name: "vql-coach", module: "src/elements/coach.ts", budget: 1280 }, // measured 999 B
  { name: "vql-captions", module: "src/elements/captions-feature.ts", budget: 3328 }, // measured 2843 B
  { name: "vql-mic-pill", module: "src/elements/mic-pill.ts", budget: 1280 }, // measured 940 B
];

/** Today's gzipped size, plus 10%, rounded up to the next 256 B. */
const proposed = (gz) => Math.ceil((gz * 1.1) / 256) * 256;

async function bundle(file) {
  return build({
    absWorkingDir: root,
    entryPoints: [file],
    bundle: true,
    minify: true,
    format: "esm",
    target: "es2022",
    write: false,
    outdir: "size-out",
    splitting: true,
    metafile: true,
    // The avatar is an optional peer loaded at run time, never bundled; React
    // is the page's own.
    external: ["@voqalize/avatar", "react", "react-dom", "react/jsx-runtime"],
    define: { "process.env.NODE_ENV": '"production"' },
    conditions: ["production"],
    logLevel: "silent",
  });
}

/** Output path (relative, as the metafile has it) → its bytes. */
function outputs(result) {
  const files = new Map();
  for (const f of result.outputFiles) files.set(relative(root, f.path), f.contents);
  return files;
}

/** An output and everything it imports statically, transitively. */
function staticClosure(meta, start) {
  const seen = new Set();
  const stack = [start];
  while (stack.length) {
    const path = stack.pop();
    if (seen.has(path)) continue;
    seen.add(path);
    for (const imp of meta.outputs[path]?.imports ?? []) {
      if (imp.kind === "import-statement" && !imp.external) stack.push(imp.path);
    }
  }
  return seen;
}

const gzipOf = (files, paths) => {
  const code = Buffer.concat([...paths].map((p) => files.get(p) ?? Buffer.alloc(0)));
  return { min: code.length, gz: gzipSync(code, { level: 9 }).length };
};

let over = false;
const rows = [];
function report(name, size, budget) {
  const ok = size.gz <= budget;
  if (!ok) over = true;
  rows.push({ name, min: size.min, gz: size.gz, budget, verdict: ok ? "within" : "OVER", propose: proposed(size.gz) });
}

let lazyMeasured = false;
for (const entry of ENTRIES) {
  const result = await bundle(entry.file);
  const meta = result.metafile;
  const files = outputs(result);
  const main = Object.keys(meta.outputs).find((p) => meta.outputs[p].entryPoint === entry.file);
  if (!main) throw new Error(`no output for ${entry.file}`);
  const upFront = staticClosure(meta, main);
  report(`${entry.name} (up front)`, gzipOf(files, upFront), entry.budget);

  if (entry.file !== "scripts/size-elements.ts") continue;
  lazyMeasured = true;
  for (const lazy of LAZY) {
    const out = Object.keys(meta.outputs).find((p) => meta.outputs[p].entryPoint === lazy.module);
    if (!out) {
      console.error(`${lazy.name}: ${lazy.module} is not a lazy chunk of the widget's build`);
      over = true;
      continue;
    }
    const own = [...staticClosure(meta, out)].filter((p) => !upFront.has(p));
    report(`${lazy.name} (lazy)`, gzipOf(files, own), lazy.budget);
  }
}
if (!lazyMeasured) throw new Error("the widget's entry was not measured");

const width = Math.max(...rows.map((r) => r.name.length));
for (const r of rows) {
  const tail = propose ? `proposed ${r.propose} B` : `budget ${r.budget} B: ${r.verdict}`;
  console.log(`${r.name.padEnd(width)}  ${String(r.min).padStart(7)} B min  ${String(r.gz).padStart(6)} B gz  (${tail})`);
}
process.exit(over && !propose ? 1 : 0);
