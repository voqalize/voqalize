import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { avatarRuntime } from "../../shared/avatar-runtime.mjs";
import { noDaily } from "../../shared/no-daily.mjs";

// Kosha Homes has real URLs (/demos/property/listing/<id>, /project/<id>…). The
// app routes on the path and `scripts/route-shells.mjs` writes a copy of
// index.html at every route after the build, so a deep link or a refresh on
// static hosting finds a file of its own. The data (../data/homes.json) and the
// persona (../persona.json) live outside this app and are imported directly.
export default defineConfig({
  base: "/demos/property/",
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
    fs: { allow: ["..", "../../shared"] },
    proxy: {
      "/api": {
        target: process.env.VOQALIZE_API_TARGET ?? "http://localhost:8274",
        changeOrigin: true,
      },
    },
  },
});
