import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { avatarRuntime } from "../../shared/avatar-runtime.mjs";
import { noDaily } from "../../shared/no-daily.mjs";

// Fashio has real URLs (/demos/fashio/p/<id>, /shop/<dept>/<type>…). The app
// routes on the path and `scripts/route-shells.mjs` writes a copy of index.html
// at the static routes after the build. The catalogue is fetched from the
// public bucket; on hosts its CORS does not allow (localhost, a tunnel) the
// page fetches `/demos/fashio/fashio-assets/*` instead, which this proxies to
// the bucket in dev and preview (`src/data/assets.ts` picks the base).
export default defineConfig({
  base: "/demos/fashio/",
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
  preview: {
    allowedHosts: [".local.voqalize.com"],
    proxy: {
      "/demos/fashio/fashio-assets": {
        target: "https://storage.googleapis.com",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/demos\/fashio\/fashio-assets/, "/voqalize-fashio-assets"),
      },
    },
  },
  server: {
    allowedHosts: [".local.voqalize.com"],
    fs: { allow: ["..", "../../shared"] },
    proxy: {
      "/demos/fashio/fashio-assets": {
        target: "https://storage.googleapis.com",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/demos\/fashio\/fashio-assets/, "/voqalize-fashio-assets"),
      },
      "/api": {
        target: process.env.VOQALIZE_API_TARGET ?? "http://localhost:8274",
        changeOrigin: true,
      },
    },
  },
});
