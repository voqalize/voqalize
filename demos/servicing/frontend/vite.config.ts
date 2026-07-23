import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/servicing/` so the assembled MPA serves it at
// `https://<host>/demos/servicing` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/servicing/`.
export default defineConfig({
  base: "/demos/servicing/",
  plugins: [react()],
  server: {
    port: 5754,
    // Session-bootstrap API is proxied to the local control plane in dev.
    proxy: {
      "/api": { target: "http://localhost:8274", changeOrigin: true },
    },
  },
});
