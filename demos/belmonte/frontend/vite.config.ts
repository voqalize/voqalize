import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { avatarRuntime } from "../../shared/avatar-runtime.mjs";
import { noDaily } from "../../shared/no-daily.mjs";

// Hotel Belmonte routes on the path (/demos/belmonte/dining, /stay/check-in…);
// scripts/route-shells.mjs writes a copy of index.html at each after the build,
// so a refresh on static hosting finds a file of its own. The hotel's data and
// the persona live beside this app (../data, ../persona.json) and are read by
// the brain too, so the dev server may serve the folder above.
export default defineConfig({
  base: "/demos/belmonte/",
  publicDir: "../../public",
  plugins: [react(), avatarRuntime(), noDaily()],
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("hotel.json")) return "hotel";
          if (id.includes("node_modules/react") || id.includes("react-router")) return "react";
        },
      },
    },
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
