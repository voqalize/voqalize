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
 * The React SDK (`sdk/react`) is built first because each demo depends on it by
 * path (`file:../../../sdk/react`) and resolves the freshly built `dist/`.
 *
 * Per-demo wiring is baked at build (Vite inlines `import.meta.env.VITE_*`). Each
 * app reads the generic `VITE_TENANT` / `VITE_AGENT_ID` / `VITE_PUBLISHABLE_KEY`;
 * when building all demos at once we map each demo's values from the per-demo
 * `VITE_<NAME>_AGENT` / `VITE_<NAME>_PK` (and `VITE_DEMO_TENANT`) env — the same
 * interface the cloudbuild passes through. Missing values just leave a demo
 * unprovisioned (its UI shows a clear "publishableKey is required" error).
 */

import { execSync } from "node:child_process";
import { cpSync, mkdirSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const demosDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = dirname(demosDir);
const distDir = join(demosDir, "dist");

const manifest = JSON.parse(readFileSync(join(demosDir, "manifest.json"), "utf8"));
const demoNames = manifest.demos.map((d) => d.name);

const tenant = process.env.VITE_DEMO_TENANT ?? process.env.VITE_TENANT ?? "demo";

function run(cmd, cwd, extraEnv = {}) {
  console.log(`\n$ ${cmd}\n  (cwd: ${cwd.replace(repoRoot, ".")})`);
  execSync(cmd, { cwd, stdio: "inherit", env: { ...process.env, ...extraEnv } });
}

/** Install (standalone, outside any workspace) and build one Vite app, then copy
 *  its `dist/` into the assembled tree at `outDir`. */
function buildApp(appDir, outDir, env = {}) {
  run("pnpm install --ignore-workspace", appDir);
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
 * Guard against the regression where a demo renders Tailwind-styled voice-ui-kit
 * components but never imports the kit's stylesheet — Vite then emits no CSS
 * chunk at all and the widget renders as raw browser defaults. Deliberately
 * coarse: if the source either imports a `voice-ui-kit/styles*` bundle or
 * renders `UserAudioControl`, the build output must contain at least one CSS
 * asset.
 */
function assertStylesheetShipped(name, appDir, outDir) {
  const src = readSource(appDir);
  const needsCss =
    /@pipecat-ai\/voice-ui-kit\/styles/.test(src) || /<UserAudioControl[\s/>]/.test(src);
  if (!needsCss) return;
  const assets = join(outDir, "assets");
  const css = readdirSync(assets, { withFileTypes: true }).filter(
    (e) => e.isFile() && e.name.endsWith(".css"),
  );
  if (css.length === 0) {
    throw new Error(
      `${name}: uses @pipecat-ai/voice-ui-kit UI but built no CSS asset — ` +
        `the kit's components will render unstyled. Import ` +
        `"@pipecat-ai/voice-ui-kit/styles.scoped" and wrap the widget in a ` +
        `.vkui-root element.`,
    );
  }
  console.log(`  ✓ ${name}: voice-ui-kit stylesheet shipped (${css.map((e) => e.name).join(", ")})`);
}

// 1. The SDK every demo links to by path — build first so `file:` deps see it.
run("pnpm install --ignore-workspace", join(repoRoot, "sdk", "react"));
run("pnpm build", join(repoRoot, "sdk", "react"));

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
    VITE_TENANT: tenant,
    VITE_AGENT_ID: process.env[`VITE_${up}_AGENT`] ?? "",
    VITE_PUBLISHABLE_KEY: process.env[`VITE_${up}_PK`] ?? "",
  });
  assertStylesheetShipped(name, appDir, outDir);
}

console.log(`\n✓ assembled ${demoNames.length} demos → ${distDir.replace(repoRoot, ".")}`);
