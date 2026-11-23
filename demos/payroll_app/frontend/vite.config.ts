import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { avatarRuntime } from "../../shared/avatar-runtime.mjs";
import { noDaily } from "../../shared/no-daily.mjs";

// Paynora is the product itself, signed in as an HR admin, with real URLs
// (/demos/payroll_app/payslips/BB-1030/2026-01, /tax/regime/BB-1007…). The app
// routes on the path (BrowserRouter with this base), and
// scripts/route-shells.mjs writes a copy of index.html at every route after the
// build, so a deep link or a refresh on static hosting finds a file of its own.
// The dev port is passed on the command line (`pnpm dev --port 5403`), never
// written here.
export default defineConfig({
  base: "/demos/payroll_app/",
  publicDir: "../../public",
  plugins: [react(), avatarRuntime(), noDaily()],
  build: {
    chunkSizeWarningLimit: 900,
  },
  server: {
    allowedHosts: [".local.voqalize.com"],
    // ../data/*.json (company, product), ../../persona.json and the shared kit
    // live outside this app.
    fs: { allow: ["..", "../../shared"] },
    proxy: {
      "/api": {
        target: process.env.VOQALIZE_API_TARGET ?? "http://localhost:8274",
        changeOrigin: true,
      },
    },
  },
});
