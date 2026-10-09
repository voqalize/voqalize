// Builds the unpacked extension into dist/: one bundled content script and the
// manifest, stamped with this package's version. Beside it, dist/embed/ holds
// the same bundle as the one script Qween embeds on their own pages, before
// `</body>`.
//
// The agent id and publishable key are read from the environment (or a local
// .env beside this file) and baked into the bundle, exactly as the demo UIs'
// Vite builds bake theirs. A build without them fails, because an extension
// that loads and then cannot start a call looks like a broken site.

import { build } from "esbuild";
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "dist");

function readEnv() {
  const env = { ...process.env };
  const file = join(here, ".env");
  if (existsSync(file)) {
    for (const line of readFileSync(file, "utf8").split("\n")) {
      const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);
      if (m && !env[m[1]]) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
  }
  return env;
}

const env = readEnv();
const wiring = {
  apiBase: env.VOQALIZE_API_BASE || "https://app.dev.voqalize.com/api/v1",
  agentId: env.VOQALIZE_AGENT_ID || "",
  publishableKey: env.VOQALIZE_PUBLISHABLE_KEY || "",
};
if (!wiring.agentId || !wiring.publishableKey) {
  console.error("VOQALIZE_AGENT_ID and VOQALIZE_PUBLISHABLE_KEY are required (see .env.example).");
  process.exit(1);
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

const bundle = {
  entryPoints: [join(here, "src/content.ts")],
  bundle: true,
  // A MAIN-world content script is a classic script, and so is a plain
  // `<script src>`, so the bundle is one IIFE. The avatar's runtime is still a
  // dynamic import from its own host, which a classic script may make.
  format: "iife",
  minify: true,
  legalComments: "none",
  define: { __VOQALIZE__: JSON.stringify(wiring) },
};
await build({ ...bundle, outfile: join(out, "content.js"), target: "chrome120" });
// The embed reaches every shopper's browser, not only desktop Chrome.
await build({
  ...bundle,
  outfile: join(out, "embed", "qween-trisha.js"),
  target: ["chrome100", "safari15", "firefox100"],
});

const pkg = JSON.parse(readFileSync(join(here, "package.json"), "utf8"));
const manifest = JSON.parse(readFileSync(join(here, "manifest.json"), "utf8"));
manifest.version = pkg.version;
writeFileSync(join(out, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
copyFileSync(join(here, "README.md"), join(out, "README.md"));

console.log(`built ${out} and ${join(out, "embed", "qween-trisha.js")} (${wiring.apiBase})`);
