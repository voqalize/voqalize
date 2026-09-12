import react from "@vitejs/plugin-react";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, searchForWorkspaceRoot } from "vite";

// The avatar checkout beside this one, in the four-sibling layout. When it is
// there, `vite dev` serves tara from its source instead of the vendored build,
// so an edit to her rig or to the mixer shows on the next reload with nothing
// rebuilt. `vite build` never looks at it: what ships is always `vendor/tara/`.
// `TARA_VENDORED=1` runs the dev server against the vendored build instead.
const AVATAR = fileURLToPath(new URL("../../../../avatar", import.meta.url));
const TARA_SOURCE = `${AVATAR}/packages/avatar-3d/src/tara.ts`;

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/aura/` so the assembled MPA serves it at
// `https://<host>/demos/aura` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/aura/`.
export default defineConfig(({ command }) => {
  const fromSource = command === "serve" && !process.env.TARA_VENDORED && existsSync(TARA_SOURCE);
  return {
    base: "/demos/aura/",
    plugins: [react()],
    resolve: fromSource
      ? {
          alias: [
            { find: /^\.\/vendor\/tara\/tara\.js$/, replacement: TARA_SOURCE },
            // The mixer's TypeScript rather than its tsc output, which would
            // otherwise need a build to show a change.
            {
              find: /^@voqalize\/avatar\/internal$/,
              replacement: `${AVATAR}/packages/avatar/client/internal.ts`,
            },
          ],
        }
      : undefined,
    build: {
      // voice-ui-kit's scoped stylesheet is authored with native CSS nesting.
      // Vite's default CSS target (safari14) cannot lower one of its rules and
      // warns on every build; it emits the nesting untouched either way, so the
      // only thing a modern target changes is the noise in the log.
      cssTarget: "chrome112",
    },
    server: {
      // Vite rejects unknown Host headers; allow the local nginx front.
      allowedHosts: [".local.voqalize.com"],
      fs: fromSource ? { allow: [searchForWorkspaceRoot(process.cwd()), AVATAR] } : undefined,
      // Session-bootstrap API is proxied to the local control plane in dev.
      proxy: {
        "/api": { target: "http://localhost:8274", changeOrigin: true },
      },
    },
  };
});
