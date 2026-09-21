import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/travel/` so the assembled MPA serves it at
// `https://<host>/demos/travel` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/travel/`.
export default defineConfig({
  base: "/demos/travel/",
  // The gallery's favicon, in ONE place. Every demo builds under its own
  // `base`, so vite rewrites the root-relative hrefs in index.html to
  // `/demos/<name>/favicon.ico` and each demo ships its own copy of the file —
  // but there is only one file in the tree to keep current. A demo that wants
  // assets of its own points this at a directory beside its index.html.
  publicDir: "../../public",
  plugins: [react()],
  // Tess fetches her GLB with `new URL("…", import.meta.url)`, which esbuild's
  // dependency pre-bundling cannot follow — it inlines a path that is not there.
  // Excluding the package keeps Vite serving its real files.
  optimizeDeps: { exclude: ["@voqalize/avatar"] },
  server: {
    // Vite rejects unknown Host headers; allow the local nginx front.
    allowedHosts: [".local.voqalize.com"],
    // Session-bootstrap API is proxied to the local control plane in dev.
    proxy: {
      "/api": { target: "http://localhost:8274", changeOrigin: true },
    },
  },
});
