// Builds the unpacked extension into dist/: four bundles and the manifest,
// stamped with this package's version.
//
//   content.js     the call, the widget and the site adapter, in the page's
//                  own JavaScript world (MAIN);
//   bridge.js      the isolated-world script that carries the page's messages
//                  to the hub and back;
//   anchor.js      marks what the adapters match on `translate="no"` from
//                  document_start, before Chrome's translator reaches it;
//   background.js  the hub: one call relayed across every Cannon Home tab
//                  (cannonhome.cl and www.cannonhome.cl), and new tabs opened
//                  for Javier's moves.
//
// rules.json (copied as is) removes the site's Content-Security-Policy on its
// pages, which would otherwise block the call in the page's world.
//
// The agent id and publishable key are read from the environment (or a local
// .env beside this file) and baked into content.js. A build without them still
// succeeds, with a warning, so the adapter can be driven from the console
// before an agent exists; the widget then says the call cannot start.
//
// VOQALIZE_ENV_FILE and VOQALIZE_OUT_DIR point a build at another key and
// another directory (`build:prod` uses them for production).
//
// AVATAR_RUNTIME, when set, swaps the avatar runtime the npm shim names for
// another — `pnpm build` sets it to the dev host's `current.js`, so the dev
// extension runs the last dev upload. Read from the process alone, never from a
// .env file, so a production build cannot pick it up by accident.

import { build } from "esbuild";
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { unreleasedRuntime } from "../../shared/avatar-runtime.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const out = process.env.VOQALIZE_OUT_DIR || join(here, "dist");

function readEnv() {
  const env = { ...process.env };
  const file = process.env.VOQALIZE_ENV_FILE || join(here, ".env");
  if (existsSync(file)) {
    for (const line of readFileSync(file, "utf8").split("\n")) {
      const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);
      if (m && !env[m[1]]) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
  }
  return env;
}

const env = readEnv();
const avatarRuntime = process.env.AVATAR_RUNTIME || "";
if (avatarRuntime) unreleasedRuntime(avatarRuntime);
const wiring = {
  apiBase: env.VOQALIZE_API_BASE || "https://app.dev.voqalize.com/api/v1",
  agentId: env.VOQALIZE_AGENT_ID || "",
  publishableKey: env.VOQALIZE_PUBLISHABLE_KEY || "",
};
if (!wiring.agentId || !wiring.publishableKey) {
  console.warn(
    "warning: VOQALIZE_AGENT_ID or VOQALIZE_PUBLISHABLE_KEY is empty (see .env.example); " +
      "the extension builds, and its calls will not start.",
  );
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

// The shim names its runtime in one module, `@voqalize/avatar/dist/pin.js`.
const PIN = /[\\/]@voqalize[\\/]avatar[\\/]dist[\\/]pin\.js$/;
const URL_LINE = /export const RUNTIME_URL = "[^"]*";/;
const runtimeOverride = {
  name: "voqalize-avatar-runtime",
  setup(b) {
    b.onLoad({ filter: PIN }, ({ path }) => {
      const source = readFileSync(path, "utf8");
      if (!URL_LINE.test(source)) throw new Error(`${path}: no RUNTIME_URL to override`);
      const url = JSON.stringify(avatarRuntime);
      return { contents: source.replace(URL_LINE, `export const RUNTIME_URL = ${url};`), loader: "js" };
    });
  },
};

const common = { bundle: true, minify: true, legalComments: "none", target: "chrome120" };

// A MAIN-world content script is a classic script, so the bundle is one IIFE.
// The avatar's runtime is still a dynamic import from its own host.
await build({
  ...common,
  entryPoints: [join(here, "src/content.ts")],
  format: "iife",
  define: { __VOQALIZE__: JSON.stringify(wiring) },
  plugins: avatarRuntime ? [runtimeOverride] : [],
  outfile: join(out, "content.js"),
});
await build({ ...common, entryPoints: [join(here, "src/bridge.ts")], format: "iife", outfile: join(out, "bridge.js") });
await build({ ...common, entryPoints: [join(here, "src/anchor.ts")], format: "iife", outfile: join(out, "anchor.js") });
await build({ ...common, entryPoints: [join(here, "src/background.ts")], format: "esm", outfile: join(out, "background.js") });

const pkg = JSON.parse(readFileSync(join(here, "package.json"), "utf8"));
const manifest = JSON.parse(readFileSync(join(here, "manifest.json"), "utf8"));
manifest.version = pkg.version;
writeFileSync(join(out, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
copyFileSync(join(here, "README.md"), join(out, "README.md"));
if (existsSync(join(here, "rules.json"))) copyFileSync(join(here, "rules.json"), join(out, "rules.json"));

console.log(`built ${out} (${wiring.apiBase})`);
console.log(`avatar runtime: ${avatarRuntime || "the npm pin"}`);
