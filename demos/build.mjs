#!/usr/bin/env node
/**
 * Assemble the demo UIs — every demo is a self-contained Vite app under
 * `demos/<name>/frontend/`, built at base `/demos/<name>/`. This script builds them
 * all and lays the output out under `demos/dist/demos/<name>/`:
 *
 *     demos/dist/
 *       demos/<name>/index.html, assets/…   ← each demo (base /demos/<name>/)
 *
 * There is no landing page here — the marketing site owns the `/demos` index and
 * weaves the demos into its story. The private marketing build downloads this
 * assembled `dist/` (as a versioned artifact) and lays it under the apex domain at
 * `/demos/<name>`, so the browser loads a demo same-origin with marketing + docs.
 *
 * Each demo depends on `@voqalize/client-react` by **published version range**,
 * exactly as a customer's app would — a demo is read and copied, and a `file:`
 * path is not something anyone can copy. So that this repo still tests the SDK it
 * is about to publish rather than the one it published last, the build overlays
 * the locally built `sdk/react` over each install; see `overlayLocalSdk`.
 *
 * Per-demo wiring is baked at build (Vite inlines `import.meta.env.VITE_*`). Each
 * app reads the generic `VITE_AGENT_ID` / `VITE_PUBLISHABLE_KEY`; when building all
 * demos at once we map each demo's values from the per-demo `VITE_<NAME>_AGENT` /
 * `VITE_<NAME>_PK` env — the same interface the cloudbuild passes through. Missing
 * values just leave a demo unprovisioned (its UI shows a clear "publishableKey is
 * required" error).
 *
 * There is no workspace in that list any more: a `pk_` key belongs to exactly one,
 * so the control plane reads it off the key. `VITE_DEMO_TENANT` stopped being passed
 * in on 2026-08-09 and nothing here ever read it.
 */

import { execSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const demosDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = dirname(demosDir);
const distDir = join(demosDir, "dist");

const manifest = JSON.parse(readFileSync(join(demosDir, "manifest.json"), "utf8"));
const demoNames = manifest.demos.map((d) => d.name);

function run(cmd, cwd, extraEnv = {}) {
  console.log(`\n$ ${cmd}\n  (cwd: ${cwd.replace(repoRoot, ".")})`);
  execSync(cmd, { cwd, stdio: "inherit", env: { ...process.env, ...extraEnv } });
}

const sdkDir = join(repoRoot, "sdk", "react");

/**
 * Replace the installed `@voqalize/client-react` with the one built from this
 * tree.
 *
 * The demos ask npm for a published range, which is what makes them copyable —
 * but it would also mean a change to `sdk/react` was never exercised by anything
 * until after it shipped, and the break would surface in a customer's install
 * rather than in CI. Overlaying keeps both: the manifest a reader copies says
 * `^0.x`, the bytes this build compiles against are the working tree's.
 *
 * Copied rather than symlinked on purpose. A link would resolve React and pipecat
 * out of `sdk/react/node_modules`, giving the page a second copy of React and
 * every hook in the SDK an "invalid hook call". A plain directory with no
 * `node_modules` of its own leaves resolution to walk up to the demo's, which is
 * where a real install would find the peers too.
 */
function overlayLocalSdk(appDir) {
  const target = join(appDir, "node_modules", "@voqalize", "client-react");
  if (!existsSync(join(sdkDir, "dist", "index.js"))) {
    throw new Error("sdk/react was not built before the demos — nothing to overlay");
  }
  rmSync(target, { recursive: true, force: true });
  mkdirSync(target, { recursive: true });
  for (const entry of ["dist", "package.json", "README.md", "LICENSE", "CHANGELOG.md"]) {
    const from = join(sdkDir, entry);
    if (existsSync(from)) cpSync(from, join(target, entry), { recursive: true });
  }
}

/** Install (standalone, outside any workspace) and build one Vite app, then copy
 *  its `dist/` into the assembled tree at `outDir`. */
function buildApp(appDir, outDir, env = {}) {
  run("pnpm install --ignore-workspace", appDir);
  overlayLocalSdk(appDir);
  run("pnpm build", appDir, env);
  mkdirSync(outDir, { recursive: true });
  cpSync(join(appDir, "dist"), outDir, { recursive: true });
}

/** Every file under a demo's `src/`, concatenated — enough for a coarse grep. */
function readSource(appDir) {
  const walk = (dir) =>
    readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? walk(join(dir, e.name)) : [readFileSync(join(dir, e.name), "utf8")],
    );
  return walk(join(appDir, "src")).join("\n");
}

/**
 * The one voice-ui-kit export that renders no DOM of its own — it just attaches
 * the bot's audio track to a hidden `<audio>`. Every demo keeps it; none of them
 * needs the kit's stylesheet for it.
 */
const HEADLESS_KIT_EXPORTS = new Set(["BotAudioOutput"]);

/** Named bindings a demo imports from `@pipecat-ai/voice-ui-kit`. */
function kitImports(src) {
  const names = new Set();
  const re = /import\s*\{([^}]*)\}\s*from\s*["']@pipecat-ai\/voice-ui-kit["']/g;
  for (const m of src.matchAll(re)) {
    for (const part of m[1].split(",")) {
      const binding = part.trim().split(/\s+as\s+/).pop()?.trim();
      if (binding) names.add(binding);
    }
  }
  return names;
}

/**
 * Guard against the regression where a demo renders Tailwind-styled voice-ui-kit
 * components but never imports the kit's stylesheet — the components then render
 * as raw browser defaults.
 *
 * Since the catalog moved to the shared `AmbientPresence` ring (Release 3), the
 * demos render *no* styled kit component: they import only the headless
 * `BotAudioOutput`, so none of them imports a kit stylesheet and none of them
 * needs to. The old trigger (`UserAudioControl` in the source) therefore matches
 * nothing and would silently pass a demo that reintroduced, say, a
 * `<ControlBar>` — so the check now derives the trigger from the imports instead
 * of a hardcoded component name: **any** binding taken from the kit that isn't
 * on the headless allowlist and is actually rendered as JSX means styled kit UI
 * is on the page, and then both the stylesheet import and a built CSS asset are
 * required.
 */
function assertStylesheetShipped(name, appDir, outDir) {
  const src = readSource(appDir);
  const styled = [...kitImports(src)].filter(
    (n) => !HEADLESS_KIT_EXPORTS.has(n) && new RegExp(`<${n}[\\s/>]`).test(src),
  );
  const importsStyles = /@pipecat-ai\/voice-ui-kit\/styles/.test(src);

  if (styled.length === 0) {
    if (importsStyles) {
      console.log(`  · ${name}: imports the kit stylesheet but renders no kit UI — drop the import`);
    }
    return;
  }

  if (!importsStyles) {
    throw new Error(
      `${name}: renders styled @pipecat-ai/voice-ui-kit components ` +
        `(${styled.join(", ")}) but never imports the kit's stylesheet — they ` +
        `will render unstyled. Import "@pipecat-ai/voice-ui-kit/styles.scoped" ` +
        `and wrap those components in a .vkui-root element.`,
    );
  }

  const assets = join(outDir, "assets");
  const css = (existsSync(assets) ? readdirSync(assets, { withFileTypes: true }) : []).filter(
    (e) => e.isFile() && e.name.endsWith(".css"),
  );
  if (css.length === 0) {
    throw new Error(
      `${name}: renders styled @pipecat-ai/voice-ui-kit components ` +
        `(${styled.join(", ")}) but built no CSS asset — the kit's stylesheet ` +
        `import was tree-shaken or the build dropped it.`,
    );
  }
  console.log(`  ✓ ${name}: voice-ui-kit stylesheet shipped (${css.map((e) => e.name).join(", ")})`);
}

// 1. The SDK every demo installs — built first, so there is something to overlay.
run("pnpm install --ignore-workspace", sdkDir);
run("pnpm build", sdkDir);

// 1b. Then the gallery's own shared chrome, which consumes the SDK the same way
// the demos do and holds the notice-and-consent wording every demo shows before
// it opens a microphone.
run("pnpm install --ignore-workspace", join(demosDir, "shared"));
overlayLocalSdk(join(demosDir, "shared"));
run("pnpm build", join(demosDir, "shared"));

// Fresh output tree.
rmSync(distDir, { recursive: true, force: true });
mkdirSync(distDir, { recursive: true });

// 2. Each demo → dist/demos/<name>/, with its wiring mapped from per-demo env.
for (const name of demoNames) {
  console.log(`\n=== ${name} ===`);
  const up = name.toUpperCase();
  const appDir = join(demosDir, name, "frontend");
  const outDir = join(distDir, "demos", name);
  buildApp(appDir, outDir, {
    VITE_AGENT_ID: process.env[`VITE_${up}_AGENT`] ?? "",
    VITE_PUBLISHABLE_KEY: process.env[`VITE_${up}_PK`] ?? "",
  });
  assertStylesheetShipped(name, appDir, outDir);
}

console.log(`\n✓ assembled ${demoNames.length} demos → ${distDir.replace(repoRoot, ".")}`);
