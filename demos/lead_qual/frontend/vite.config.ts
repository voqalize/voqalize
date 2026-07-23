import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/lead_qual/` so the assembled MPA serves it at
// `https://<host>/demos/lead_qual` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/lead_qual/`.
export default defineConfig({
  base: "/demos/lead_qual/",
  plugins: [react()],
  server: {
    port: 5758,
    // Session-bootstrap API is proxied to the local control plane in dev.
    proxy: {
      "/api": { target: "http://localhost:8274", changeOrigin: true },
    },
  },
});
