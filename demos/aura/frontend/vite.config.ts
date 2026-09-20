import react from "@vitejs/plugin-react";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, searchForWorkspaceRoot } from "vite";

// The private avatar checkout beside this one, in the four-sibling layout. When
// it is there, `vite dev` resolves the characters and the mixer from its
// TypeScript instead of the installed `@voqalize/avatar`, so an edit to a rig or
// to the mixer shows on the next reload with nothing built or published — this
// is the loop the private repo's CLAUDE.md sends you here for. `vite build`
// never looks at it, and neither does a contributor without that checkout: both
// get the package from npm. `AVATAR_FROM_NPM=1` forces that in dev too.
const AVATAR = fileURLToPath(new URL("../../../../avatar-private", import.meta.url));
const CHARACTERS = `${AVATAR}/packages/avatar/client/three`;

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/aura/` so the assembled MPA serves it at
// `https://<host>/demos/aura` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/aura/`.
export default defineConfig(({ command }) => {
  const fromSource =
    command === "serve" && !process.env.AVATAR_FROM_NPM && existsSync(`${CHARACTERS}/tara.ts`);
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
            { find: /^@voqalize\/avatar\/avatars\/tara$/, replacement: `${CHARACTERS}/tara.ts` },
            { find: /^@voqalize\/avatar\/avatars\/tushar$/, replacement: `${CHARACTERS}/tushar.ts` },
            // Two entries and no third: a character imports the mixer by
            // relative path, so aliasing the character brings that checkout's
            // mixer, rig and clips with it. `@voqalize/avatar/react` stays on the
            // installed package, which is the half a consumer would use anyway.
          ],
        }
      : undefined,
    // The characters fetch their GLB with `new URL("…", import.meta.url)`, which
    // esbuild's dependency pre-bundling cannot follow — it inlines a path that
    // is not there. Excluding the package keeps Vite serving its real files.
    optimizeDeps: { exclude: ["@voqalize/avatar"] },
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
