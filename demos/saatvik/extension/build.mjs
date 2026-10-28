// Builds the unpacked extension into dist/: one bundled content script and the
// manifest, stamped with this package's version.
//
// The agent id and publishable key are read from the environment (or a local
// .env beside this file) and baked into the bundle, exactly as the demo UIs'
// Vite builds bake theirs. A build without them still succeeds, with a
// warning, so the extension can be built and the adapter driven from the
// console before an agent exists; the widget then says the call cannot start.
//
// VOQALIZE_ENV_FILE and VOQALIZE_OUT_DIR point a build at another key and
// another directory (`build:prod` uses them for production).
//
// AVATAR_RUNTIME, when set, swaps the avatar runtime the npm shim names for
// another — `pnpm build` sets it to the dev host's `current.js`, so the dev
// extension runs the last dev upload (see ../../shared/avatar-runtime.mjs, the
// same override for the Vite demos). Unset, as in `build:prod`, the bundle is
// exactly what npm gives a customer. Read from the process alone, never from a
// .env file, so a production build cannot pick it up by accident.
//
// pdf.js's worker is bundled as text under the module name
// `pdf-worker-source`, and the viewer starts it from a Blob, so the extension
// fetches nothing but Saatvik's own PDFs.

import { build } from "esbuild";
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { unreleasedRuntime } from "../../shared/avatar-runtime.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const out = process.env.VOQALIZE_OUT_DIR || join(here, "dist");
const require = createRequire(import.meta.url);

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

const pdfWorker = {
  name: "pdf-worker-source",
  setup(b) {
    b.onResolve({ filter: /^pdf-worker-source$/ }, () => ({
      path: require.resolve("pdfjs-dist/build/pdf.worker.min.mjs"),
      namespace: "pdf-worker-source",
    }));
    b.onLoad({ filter: /.*/, namespace: "pdf-worker-source" }, ({ path }) => ({
      contents: readFileSync(path, "utf8"),
      loader: "text",
    }));
  },
};

await build({
  entryPoints: [join(here, "src/content.ts")],
  bundle: true,
  // A MAIN-world content script is a classic script, so the bundle is one
  // IIFE. The avatar's runtime is still a dynamic import from its own host,
  // which a classic script may make.
  format: "iife",
  minify: true,
  legalComments: "none",
  target: "chrome120",
  define: { __VOQALIZE__: JSON.stringify(wiring) },
  // pdf.js reads `import.meta.url` only on its Node path, which a page never
  // takes.
  logOverride: { "empty-import-meta": "silent" },
  plugins: [pdfWorker, ...(avatarRuntime ? [runtimeOverride] : [])],
  outfile: join(out, "content.js"),
});

// The document tab (`doc.html`) runs the same viewer, with its own copy of
// pdf.js and its worker; the service worker and the bridge are small and
// have no dependencies.
await build({
  entryPoints: [join(here, "src/doc.ts")],
  bundle: true,
  format: "iife",
  minify: true,
  legalComments: "none",
  target: "chrome120",
  logOverride: { "empty-import-meta": "silent" },
  plugins: [pdfWorker],
  outfile: join(out, "doc.js"),
});
for (const name of ["background", "bridge"]) {
  await build({
    entryPoints: [join(here, `src/${name}.ts`)],
    bundle: true,
    format: "iife",
    minify: true,
    legalComments: "none",
    target: "chrome120",
    outfile: join(out, `${name}.js`),
  });
}
copyFileSync(join(here, "src/doc.html"), join(out, "doc.html"));

const pkg = JSON.parse(readFileSync(join(here, "package.json"), "utf8"));
const manifest = JSON.parse(readFileSync(join(here, "manifest.json"), "utf8"));
manifest.version = pkg.version;
writeFileSync(join(out, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
copyFileSync(join(here, "README.md"), join(out, "README.md"));
// Saatvik's pages forbid the microphone (`Permissions-Policy: microphone=()`);
// this rule lets the page itself use it and keeps the rest of their policy.
copyFileSync(join(here, "rules.json"), join(out, "rules.json"));

console.log(`built ${out} (${wiring.apiBase})`);
console.log(`avatar runtime: ${avatarRuntime || "the npm pin"}`);
