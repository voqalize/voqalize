// Builds one site's unpacked extension into dist/<site>/: the bundles, their
// two pages and the manifest, all from the site's one file
// (sites/<site>/site.ts) and the shared entry points in src/.
//
//   node build.mjs --site wom     dist/wom/
//   node build.mjs --all          every sites/*/site.ts
//   node build.mjs --site wom --out dist/wom-test   another directory (one site)
//
//   holder.js      the call, in the offscreen document `call.html`: pipecat,
//                  his voice, the relay to the pages, Stage's timeline that
//                  fires his cues as he speaks, and the tab registry;
//   content.js     the widget, his face, the Site Agent's watcher, executor
//                  and Stage moves, in the page's own JavaScript world (MAIN);
//                  it reads embed.config and mints the session;
//   shell.js       the early shell (MAIN, document_start): in a call, the
//                  widget back at once on the next page, as the last page left
//                  it, and the page load as a view transition under it;
//   bridge.js      the isolated-world script that carries the page's messages
//                  to the holder and the service worker, and back;
//   grant.js       `grant.html`, the extension's one-time microphone grant;
//   background.js  the service worker: makes the holder, opens and focuses
//                  tabs, keeps the language choice.
//
// The Site Agent snippet's source (watcher, executor, Stage moves, note cards)
// is bundled straight from a platform checkout (scripts/link-platform.mjs;
// VOQALIZE_PLATFORM_DIR to name one): nothing is loaded from elsewhere at run
// time, as MV3 requires. Its imports of `@voqalize/*` and `@pipecat-ai/*`
// resolve to this package's own copies, so there is one Stage and one pipecat
// in each bundle.
//
// The site's publishable key is read from the environment, else from
// sites/<site>/.env, else from .env beside this file (none committed), and
// baked into content.js; the agent, the site and the version come from
// embed.config at run time. A build without a key still succeeds, with a
// warning; the widget then says the call cannot start.

import { build } from "esbuild";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { linkPlatform } from "./scripts/link-platform.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(join(here, "package.json"), "utf8"));

const args = process.argv.slice(2);
const all = args.includes("--all");
const named = args.includes("--site") ? args[args.indexOf("--site") + 1] : null;
const outArg = args.includes("--out") ? args[args.indexOf("--out") + 1] : null;
const sites = all ? readdirSync(join(here, "sites")).filter((d) => existsSync(join(here, "sites", d, "site.ts"))) : named ? [named] : [];
if (!sites.length) {
  console.error("usage: node build.mjs --site <id> | --all");
  process.exit(2);
}

const platform = linkPlatform();
const snippet = join(platform, "frontend", "packages", "site-snippet", "src");
const shopifyCommon = join(platform, "frontend", "packages", "shopify-common", "src", "index.ts");
const snippetStage = join(snippet, "call", "stage.ts");

function readEnv(files) {
  const env = { ...process.env };
  for (const file of files) {
    if (!existsSync(file)) continue;
    for (const line of readFileSync(file, "utf8").split("\n")) {
      const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);
      if (m && !env[m[1]]) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
  }
  return env;
}

/** The snippet's source, this site's file, and one copy of each package. */
function resolver(siteFile) {
  return {
    name: "site-agent-resolve",
    setup(b) {
      b.onResolve({ filter: /^@site$/ }, () => ({ path: siteFile }));
      b.onResolve({ filter: /^@snippet\// }, async (a) => {
        const r = await b.resolve(`./${a.path.slice("@snippet/".length)}`, { resolveDir: snippet, kind: a.kind });
        return r.errors.length ? { errors: r.errors } : { path: r.path };
      });
      b.onResolve({ filter: /^snippet-stage-moves$/ }, () => ({ path: snippetStage }));
      b.onResolve({ filter: /^@voqalcloud\/shopify-common$/ }, () => ({ path: shopifyCommon }));
      // The snippet's own imports of the packages: this package's copies.
      b.onResolve({ filter: /^(@voqalize\/(stage|avatar|client-transport)|@pipecat-ai\/)/ }, async (a) => {
        if (a.pluginData?.ours) return undefined;
        const r = await b.resolve(a.path, { resolveDir: here, kind: a.kind, pluginData: { ours: true } });
        return r.errors.length ? { errors: r.errors } : { path: r.path };
      });
      // `call/stage.ts` keeps its two performers to itself: exported here, so
      // they run as the snippet wrote them.
      b.onLoad({ filter: /[\\/]call[\\/]stage\.ts$/ }, ({ path }) => {
        if (path !== snippetStage) return undefined;
        const source = readFileSync(path, "utf8");
        return { contents: `${source}\nexport { openPage, showRegion };\n`, loader: "ts", resolveDir: dirname(path) };
      });
    },
  };
}

async function buildSite(id) {
  const siteFile = join(here, "sites", id, "site.ts");
  if (!existsSync(siteFile)) throw new Error(`no ${siteFile}`);
  const site = (await import(pathToFileURL(siteFile).href)).default;
  if (site.id !== id) throw new Error(`${siteFile}: id is "${site.id}", not "${id}"`);
  const out = outArg && !all ? resolve(outArg) : join(here, "dist", id);
  const env = readEnv([process.env.VOQALIZE_ENV_FILE, join(here, "sites", id, ".env"), join(here, ".env")].filter(Boolean));
  const wiring = {
    apiBase: env.VOQALIZE_API_BASE || "https://app.voqalize.com/api/v1",
    publishableKey: env.VOQALIZE_PUBLISHABLE_KEY || "",
    agentId: env.VOQALIZE_AGENT_ID || "",
  };
  if (!wiring.publishableKey) {
    console.warn(
      `warning: ${id}: VOQALIZE_PUBLISHABLE_KEY is empty (see .env.example); the extension builds, and its calls will not start.`,
    );
  }

  rmSync(out, { recursive: true, force: true });
  mkdirSync(out, { recursive: true });

  const common = {
    bundle: true,
    minify: true,
    legalComments: "none",
    target: "chrome120",
    logLevel: "warning",
    // Aliases are the plugin's; the type checker's `paths` point at types.
    tsconfigRaw: { compilerOptions: {} },
    plugins: [resolver(siteFile)],
  };
  const entry = (name) => join(here, "src", `${name}.ts`);
  // A MAIN-world content script is a classic script, so the bundle is one
  // IIFE. The avatar's runtime is still a dynamic import from its own host.
  await build({ ...common, entryPoints: [entry("content")], format: "iife", define: { __VOQALIZE__: JSON.stringify(wiring) }, outfile: join(out, "content.js") });
  await build({ ...common, entryPoints: [entry("holder")], format: "iife", outfile: join(out, "holder.js") });
  await build({ ...common, entryPoints: [entry("grant")], format: "iife", outfile: join(out, "grant.js") });
  await build({ ...common, entryPoints: [entry("shell")], format: "iife", outfile: join(out, "shell.js") });
  await build({ ...common, entryPoints: [entry("bridge")], format: "iife", outfile: join(out, "bridge.js") });
  await build({ ...common, entryPoints: [entry("background")], format: "esm", outfile: join(out, "background.js") });

  const manifest = {
    manifest_version: 3,
    name: `Javier para ${site.siteName} — Voqalize preview`,
    version: pkg.version,
    description: site.description,
    key: site.manifestKey,
    background: { service_worker: "background.js", type: "module" },
    content_scripts: [
      { matches: site.matches, js: ["bridge.js"], run_at: "document_start" },
      { matches: site.matches, js: ["shell.js"], run_at: "document_start", world: "MAIN" },
      { matches: site.matches, js: ["content.js"], run_at: "document_idle", world: "MAIN" },
    ],
    permissions: ["storage", "offscreen"],
    host_permissions: site.matches,
    web_accessible_resources: [{ resources: ["grant.html", "grant.js"], matches: site.matches }],
  };
  writeFileSync(join(out, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  copyFileSync(join(here, "src", "call.html"), join(out, "call.html"));
  const g = site.grantStyle;
  const grant = readFileSync(join(here, "src", "grant.html"), "utf8")
    .replaceAll("__FONT__", g.font)
    .replaceAll("__INK__", g.ink)
    .replaceAll("__BUTTON__", g.button)
    .replaceAll("__ON_BUTTON__", g.onButton);
  writeFileSync(join(out, "grant.html"), grant);
  copyFileSync(join(here, "README.md"), join(out, "README.md"));
  console.log(`built ${out} (${wiring.apiBase}; extension id ${site.extensionId})`);
}

for (const id of sites) await buildSite(id);
