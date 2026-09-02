import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/avatar/` so the assembled MPA serves it at
// `https://<host>/demos/avatar` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/avatar/`.
//
// The nine avatars are dynamically imported, one module each, so a visitor
// downloads the face they are looking at rather than all nine — six of them are
// canvas avatars carrying wardrobe images, and shipping every one up front
// would put megabytes in front of the greeting.
export default defineConfig({
  base: "/demos/avatar/",
  plugins: [react()],
  optimizeDeps: {
    // A canvas avatar locates its rig JSON and wardrobe images with
    // `new URL('../src/canvas/data/…', import.meta.url)`. Vite's dev-time
    // pre-bundler copies the module into `node_modules/.vite/deps/`, and that
    // URL then resolves against the copy — the rig 404s into the SPA fallback,
    // the canvas mounts and paints nothing, and no error is thrown. Excluding
    // the package leaves it served from its real path, where the URL is right.
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
