import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { avatarRuntime } from "../../shared/avatar-runtime.mjs";
import { noDaily } from "../../shared/no-daily.mjs";

// Tankora is a marketing site with real URLs (/demos/payroll_site/pricing,
// /modules/<id>…): the app routes on the path, and scripts/route-shells.mjs
// writes a copy of index.html at every route after the build so a deep link
// or a refresh on static hosting finds a file of its own. The dev port is
// passed on the command line (ecosystem.config.cjs), never written here.
export default defineConfig({
  base: "/demos/payroll_site/",
  publicDir: "../../public",
  plugins: [react(), avatarRuntime(), noDaily()],
  build: {
    chunkSizeWarningLimit: 800,
  },
  server: {
    allowedHosts: [".local.voqalize.com"],
    // product.json, tax_example.json, site.json and persona.json live beside this app.
    fs: { allow: [".."] },
    proxy: {
      "/api": {
        target: process.env.VOQALIZE_API_TARGET ?? "http://localhost:8274",
        changeOrigin: true,
      },
    },
  },
});
