#!/usr/bin/env node
/**
 * Assemble the demos MPA — every demo is a self-contained Vite app under
 * `demos/<name>/frontend/`, built at base `/demos/<name>/`, plus the landing app
 * at `demos/landing/frontend/` built at `/`. This script builds them all and
 * lays the output out the way the umbrella backend serves it:
 *
 *     demos/dist/
 *       index.html, assets/…            ← landing (base /)
 *       demos/<name>/index.html, …      ← each demo (base /demos/<name>/)
 *
 * The React SDK (`sdk/react`) is built first because each demo depends on it by
 * path (`file:../../../sdk/react`) and resolves the freshly built `dist/`.
 *
 * Per-demo wiring is baked at build (Vite inlines `import.meta.env.VITE_*`). Each
 * app reads the generic `VITE_TENANT` / `VITE_AGENT_ID` / `VITE_PUBLISHABLE_KEY`;
 * when building all demos at once we map each demo's values from the per-demo
 * `VITE_<NAME>_AGENT` / `VITE_<NAME>_PK` (and `VITE_DEMO_TENANT`) env — the same
 * interface the Dockerfile and cloudbuild pass through. Missing values just leave
 * a demo unprovisioned (its UI shows a clear "publishableKey is required" error).
 */

import { execSync } from "node:child_process";
import { cpSync, mkdirSync, readFileSync, rmSync } from "node:fs";
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

// 1. The SDK every demo links to by path — build first so `file:` deps see it.
run("pnpm install --ignore-workspace", join(repoRoot, "sdk", "react"));
run("pnpm build", join(repoRoot, "sdk", "react"));

// Fresh output tree.
rmSync(distDir, { recursive: true, force: true });
mkdirSync(distDir, { recursive: true });

// 2. Landing app → dist/ (site root).
console.log("\n=== landing ===");
buildApp(join(demosDir, "landing", "frontend"), distDir);

// 3. Each demo → dist/demos/<name>/, with its wiring mapped from per-demo env.
for (const name of demoNames) {
  console.log(`\n=== ${name} ===`);
  const up = name.toUpperCase();
  buildApp(join(demosDir, name, "frontend"), join(distDir, "demos", name), {
    VITE_TENANT: tenant,
    VITE_AGENT_ID: process.env[`VITE_${up}_AGENT`] ?? "",
    VITE_PUBLISHABLE_KEY: process.env[`VITE_${up}_PK`] ?? "",
  });
}

console.log(`\n✓ assembled ${demoNames.length} demos + landing → ${distDir.replace(repoRoot, ".")}`);
