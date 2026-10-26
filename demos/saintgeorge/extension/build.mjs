// Builds the unpacked extension into dist/: the bundles, their two pages and
// the manifest, stamped with this package's version.
//
//   holder.js      the call, in the offscreen document `call.html`: pipecat,
//                  his voice, the relay to the pages, the routing of the
//                  brain's Actions, the narration and the tab registry;
//   content.js     the widget, his face and the site adapter, in the page's
//                  own JavaScript world (MAIN); it mints the session;
//   shell.js       the early shell (MAIN, document_start): in a call, the
//                  widget back at once on the next page, as the last page left
//                  it, and the page load as a view transition under it;
//   bridge.js      the isolated-world script that carries the page's messages
//                  to the holder and the service worker, and back;
//   anchor.js      marks what the adapter matches on `translate="no"` from
//                  document_start, before Chrome's translator reaches it;
//   grant.js       `grant.html`, the extension's one-time microphone grant;
//   background.js  the service worker: makes the holder, opens and focuses
//                  tabs, reads the school's public calendar for the page, keeps
//                  the language choice.
//
// The site sends no Permissions-Policy (checked on every page, 2026-10-22), so
// the grant frame's `allow="microphone"` needs no header rule here.
//
// The agent id and publishable key are read from the environment (or a local
// .env beside this file) and baked into content.js. A build without them still
// succeeds, with a warning, so the adapter can be driven from the console
// before an agent exists; the widget then says the call cannot start.
//
// VOQALIZE_ENV_FILE and VOQALIZE_OUT_DIR point a build at another key and
// another directory (`build:prod` uses them for production).
//
// VOQALIZE_TEST_BUILD=1 builds the extension the end-to-end tests load
// (test/.build/ext): a stand-in call in the holder (test/fake-call-client.ts),
// a stand-in avatar, and a made-up API, so nothing reaches the network.
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
const out =
  process.env.VOQALIZE_TEST_BUILD === "1"
    ? join(here, "test", ".build", "ext")
    : process.env.VOQALIZE_OUT_DIR || join(here, "dist");

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
const testBuild = process.env.VOQALIZE_TEST_BUILD === "1";
const avatarRuntime = testBuild ? "" : process.env.AVATAR_RUNTIME || "";
if (avatarRuntime) unreleasedRuntime(avatarRuntime);
const wiring = testBuild
  ? { apiBase: "https://api.voqalize.test/api/v1", agentId: "test-agent", publishableKey: "pk_test" }
  : {
      apiBase: env.VOQALIZE_API_BASE || "https://app.dev.voqalize.com/api/v1",
      agentId: env.VOQALIZE_AGENT_ID || "",
      publishableKey: env.VOQALIZE_PUBLISHABLE_KEY || "",
    };
// His mouth strip for the still a page shows until its face draws
// (`src/mouth.ts`), on the avatar host this build's runtime comes from: the
// dev host for `pnpm build` (AVATAR_RUNTIME), the host the npm shim pins for
// `build:prod`, and the tests' stand-in host for theirs.
const STRIP_PATH = "/characters/javier-mouth-strip.f0985aa96df7.webp";
function pinnedRuntime() {
  const pin = readFileSync(join(here, "node_modules", "@voqalize", "avatar", "dist", "pin.js"), "utf8");
  const m = pin.match(/export const RUNTIME_URL = "([^"]*)";/);
  if (!m) throw new Error("@voqalize/avatar/dist/pin.js: no RUNTIME_URL to take the avatar host from");
  return m[1];
}
const mouthStrip = testBuild
  ? `https://avatar.voqalize.test${STRIP_PATH}`
  : new URL(STRIP_PATH, avatarRuntime || pinnedRuntime()).href;
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

// The tests' stand-ins: the call in the holder, and the avatar.
const standIns = {
  name: "voqalize-test-stand-ins",
  setup(b) {
    b.onResolve({ filter: /^\.\/call-client$/ }, () => ({ path: join(here, "test", "fake-call-client.ts") }));
    b.onResolve({ filter: /^@voqalize\/avatar$/ }, () => ({ path: join(here, "test", "fake-avatar.ts") }));
  },
};
const plugins = testBuild ? [standIns] : avatarRuntime ? [runtimeOverride] : [];

// A MAIN-world content script is a classic script, so the bundle is one IIFE.
// The avatar's runtime is still a dynamic import from its own host.
await build({
  ...common,
  entryPoints: [join(here, "src/content.ts")],
  format: "iife",
  define: { __VOQALIZE__: JSON.stringify(wiring), __MOUTH_STRIP__: JSON.stringify(mouthStrip) },
  plugins,
  outfile: join(out, "content.js"),
});
// The holder is a classic script in `call.html`.
await build({ ...common, entryPoints: [join(here, "src/holder.ts")], format: "iife", plugins, outfile: join(out, "holder.js") });
await build({ ...common, entryPoints: [join(here, "src/grant.ts")], format: "iife", outfile: join(out, "grant.js") });
// The early shell, also in the page's world, at document_start: in a call,
// the widget as the last page left it, before the page has parsed.
await build({
  ...common,
  entryPoints: [join(here, "src/shell.ts")],
  format: "iife",
  define: { __MOUTH_STRIP__: JSON.stringify(mouthStrip) },
  outfile: join(out, "shell.js"),
});
await build({ ...common, entryPoints: [join(here, "src/bridge.ts")], format: "iife", outfile: join(out, "bridge.js") });
await build({ ...common, entryPoints: [join(here, "src/anchor.ts")], format: "iife", outfile: join(out, "anchor.js") });
await build({ ...common, entryPoints: [join(here, "src/background.ts")], format: "esm", outfile: join(out, "background.js") });

const pkg = JSON.parse(readFileSync(join(here, "package.json"), "utf8"));
const manifest = JSON.parse(readFileSync(join(here, "manifest.json"), "utf8"));
manifest.version = pkg.version;
writeFileSync(join(out, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
copyFileSync(join(here, "README.md"), join(out, "README.md"));
for (const page of ["call.html", "grant.html"]) copyFileSync(join(here, "src", page), join(out, page));

console.log(`built ${out} (${wiring.apiBase})`);
console.log(`avatar runtime: ${avatarRuntime || "the npm pin"}`);
console.log(`mouth strip: ${mouthStrip}`);
