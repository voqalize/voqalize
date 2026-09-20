import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/legal/` so the assembled MPA serves it at
// `https://<host>/demos/legal` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/legal/`.
export default defineConfig({
  base: "/demos/legal/",
  // The gallery's favicon, in ONE place. Every demo builds under its own
  // `base`, so vite rewrites the root-relative hrefs in index.html to
  // `/demos/<name>/favicon.ico` and each demo ships its own copy of the file —
  // but there is only one file in the tree to keep current. A demo that wants
  // assets of its own points this at a directory beside its index.html.
  publicDir: "../../public",
  plugins: [react()],
  optimizeDeps: {
    // Tanya locates her `.glb` with `new URL('./assets/tanya.glb',
    // import.meta.url)`. Vite's dev-time pre-bundler copies the module into
    // `node_modules/.vite/deps/`, and that URL then resolves against the copy
    // — the model 404s into the SPA fallback, the canvas mounts and paints
    // nothing, and no error is thrown. Excluding the package leaves it served
    // from its real path, where the URL is right. The avatar demo carries the
    // same line for the same reason; the built bundle is unaffected either way.
    exclude: ["@voqalize/avatar"],
  },
  server: {
    // Vite rejects unknown Host headers; allow the local nginx front.
    allowedHosts: [".local.voqalize.com"],
    // Session-bootstrap API is proxied to the local control plane in dev.
    proxy: {
      "/api": { target: "http://localhost:8274", changeOrigin: true },
    },
  },
});
