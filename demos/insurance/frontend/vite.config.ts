import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { avatarRuntime } from "../../shared/avatar-runtime.mjs";
import { noDaily } from "../../shared/no-daily.mjs";

// Chhatri Insurance has real URLs (/demos/insurance/quote/car, /my-policies/car-2026…).
// The app routes on the path (BrowserRouter with this base) and
// `scripts/route-shells.mjs` writes a copy of index.html at every route after the
// build, so a deep link or a refresh on static hosting finds a file of its own.
const BASE = "/demos/insurance/";

export default defineConfig({
  base: BASE,
  // The gallery's shared favicon, shipped under /demos/insurance/ like every demo.
  publicDir: "../../public",
  plugins: [react(), avatarRuntime(), noDaily()],
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/react") || id.includes("react-router")) return "react";
        },
      },
    },
  },
  server: {
    allowedHosts: [".local.voqalize.com"],
    // persona.json, data/ and content/ live beside this app, read at build.
    fs: { allow: ["..", "../..", "../../shared"] },
    proxy: {
      "/api": {
        target: process.env.VOQALIZE_API_TARGET ?? "http://localhost:8274",
        changeOrigin: true,
      },
    },
  },
});
