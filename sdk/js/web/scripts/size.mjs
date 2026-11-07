// The size of each browser entry, minified and gzipped, as a page would ship
// it. The launcher has a budget because it is meant for the first paint; the
// others are reported so a change in them is seen.
//
//   pnpm size

import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = fileURLToPath(new URL("..", import.meta.url));

const ENTRIES = [
  { name: "@voqalize/web/launcher", file: "src/launcher.ts", budget: 20 * 1024 },
  // Lit and the elements; the session and the transport load only when a call starts.
  { name: "@voqalize/web/widgets (elements only)", file: "scripts/size-elements.ts" },
];

let over = false;
for (const entry of ENTRIES) {
  const result = await build({
    absWorkingDir: root,
    entryPoints: [entry.file],
    bundle: true,
    minify: true,
    format: "esm",
    target: "es2022",
    write: false,
    outdir: "size-out",
    // Split, so a dynamic import (the session, on the first call) is its own
    // chunk and is not counted against what the page loads up front.
    splitting: true,
    // The avatar is an optional peer loaded at run time, never bundled.
    external: ["@voqalize/avatar"],
    define: { "process.env.NODE_ENV": '"production"' },
    conditions: ["production"],
    logLevel: "silent",
  });
  const main = result.outputFiles.find((f) => !f.path.includes("chunk-") && f.path.endsWith(".js"));
  const shared = result.outputFiles.filter((f) => f.path.includes("chunk-"));
  // The entry and the chunks it shares with the lazy part both load up front.
  const code = Buffer.concat([main.contents, ...shared.map((f) => f.contents)]);
  const gz = gzipSync(code, { level: 9 }).length;
  const line = `${entry.name}: ${code.length} B minified, ${gz} B gzipped`;
  if (entry.budget !== undefined) {
    const ok = gz <= entry.budget;
    if (!ok) over = true;
    console.log(`${line} (budget ${entry.budget} B: ${ok ? "within" : "OVER"})`);
  } else {
    console.log(line);
  }
}
process.exit(over ? 1 : 0);
