import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { avatarRuntime } from "../../shared/avatar-runtime.mjs";
import { noDaily } from "../../shared/no-daily.mjs";

// Global Bank routes on the path (/demos/bank/app/cards, /demos/bank/loans/home…).
// `scripts/route-shells.mjs` writes a copy of index.html at every route after the
// build, so a deep link or a refresh on static hosting finds a file of its own.
// The bank's data (../data/*.json) and the persona (../persona.json) are read by
// both this page and the brain, so they live outside this app.
export default defineConfig({
  base: "/demos/bank/",
  publicDir: "../../public",
  plugins: [react(), avatarRuntime(), noDaily()],
  build: {
    chunkSizeWarningLimit: 900,
  },
  server: {
    allowedHosts: [".local.voqalize.com"],
    fs: { allow: ["..", "../../shared", "../../../sdk/js/stage"] },
    proxy: {
      "/api": {
        target: process.env.VOQALIZE_API_TARGET ?? "http://localhost:8274",
        changeOrigin: true,
      },
    },
  },
});
