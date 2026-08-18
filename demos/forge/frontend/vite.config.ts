import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/forge/` so the assembled MPA serves it at
// `https://<host>/demos/forge` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/forge/`.
export default defineConfig({
  base: "/demos/forge/",
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
