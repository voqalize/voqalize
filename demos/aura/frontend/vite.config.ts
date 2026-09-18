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
// EXPERIMENT (uncommitted): the second 3-D character, dev-only. There is no
// vendored build of him, so `vite build` cannot resolve `?avatar=tushar`.
const TUSHAR_SOURCE = `${AVATAR}/packages/avatar-3d/src/tushar.ts`;

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/aura/` so the assembled MPA serves it at
// `https://<host>/demos/aura` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/aura/`.
export default defineConfig(({ command }) => {
  const fromSource = command === "serve" && !process.env.TARA_VENDORED && existsSync(TARA_SOURCE);
  return {
    base: "/demos/aura/",
    // The gallery's favicon, in ONE place. Every demo builds under its own
    // `base`, so vite rewrites the root-relative hrefs in index.html to
    // `/demos/<name>/favicon.ico` and each demo ships its own copy of the file —
    // but there is only one file in the tree to keep current. A demo that wants
    // assets of its own points this at a directory beside its index.html.
    publicDir: "../../public",
    plugins: [react()],
    resolve: fromSource
      ? {
          alias: [
            { find: /^\.\/vendor\/tara\/tara\.js$/, replacement: TARA_SOURCE },
            { find: /^\.\/vendor\/tushar\/tushar\.js$/, replacement: TUSHAR_SOURCE },
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
