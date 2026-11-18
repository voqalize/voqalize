import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { avatarRuntime } from "../../shared/avatar-runtime.mjs";
import { noDaily } from "../../shared/no-daily.mjs";

// Varenya University has real URLs: /demos/university/programs/<id>, /apply…
// The app routes on the path (BrowserRouter with this base) and
// `scripts/route-shells.mjs` writes a copy of index.html at every route after
// the build, so a deep link or a refresh on static hosting finds a file of its own.
const BASE = "/demos/university/";

export default defineConfig({
  base: BASE,
  // The gallery's favicon, shared by every demo.
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
    // ../data/*.json and ../persona.json are imported from outside this app.
    fs: { allow: ["..", "../../shared", "../../../sdk/js/stage"] },
    proxy: {
      "/api": {
        target: process.env.VOQALIZE_API_TARGET ?? "http://localhost:8274",
        changeOrigin: true,
      },
    },
  },
});
