import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/forge/` so the assembled MPA serves it at
// `https://<host>/demos/forge` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/forge/`.
export default defineConfig({
  base: "/demos/forge/",
  // The gallery's favicon, in ONE place. Every demo builds under its own
  // `base`, so vite rewrites the root-relative hrefs in index.html to
  // `/demos/<name>/favicon.ico` and each demo ships its own copy of the file —
  // but there is only one file in the tree to keep current. A demo that wants
  // assets of its own points this at a directory beside its index.html.
  publicDir: "../../public",
  plugins: [react()],
  server: {
    // Vite rejects unknown Host headers; allow the local nginx front.
    allowedHosts: [".local.voqalize.com"],
    // Session-bootstrap API is proxied to the local control plane in dev.
    proxy: {
      "/api": { target: "http://localhost:8274", changeOrigin: true },
    },
  },
});
