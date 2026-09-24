import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// This demo is a self-contained single-page app. It builds under the relative
// base `/demos/kiosk/` so the assembled MPA serves it at
// `https://<host>/demos/kiosk` with correct asset URLs; the demos umbrella
// drops the built `dist/` into `dist/demos/kiosk/`.
export default defineConfig({
  base: "/demos/kiosk/",
  // The gallery's favicon, in ONE place. Every demo builds under its own
  // `base`, so vite rewrites the root-relative hrefs in index.html to
  // `/demos/<name>/favicon.ico` and each demo ships its own copy of the file —
  // but there is only one file in the tree to keep current. This kiosk's own
  // one static asset (the handoff QR) is imported from `src/assets` instead, so
  // it is hashed and served under this demo's base without a second public dir.
  publicDir: "../../public",
  plugins: [react()],
  // Tanvi's character module fetches its GLB with `new URL("…", import.meta.url)`,
  // which esbuild's dependency pre-bundling cannot follow — it inlines a path
  // that is not there. Excluding the package keeps Vite serving its real files.
  optimizeDeps: { exclude: ["@voqalize/avatar"] },
  build: {
    // voice-ui-kit's scoped stylesheet is authored with native CSS nesting.
    // Vite's default CSS target (safari14) cannot lower one of its rules and
    // warns on every build; a modern target only removes the noise.
    cssTarget: "chrome112",
  },
  server: {
    // Vite rejects unknown Host headers; allow the local nginx front.
    allowedHosts: [".local.voqalize.com"],
    // Session-bootstrap API is proxied to the local control plane in dev.
    // `VOQALIZE_API_TARGET=https://dev.voqalize.com` points it at hosted dev
    // instead, so a brain run through Cortex needs no local control plane at all.
    proxy: {
      "/api": {
        target: process.env.VOQALIZE_API_TARGET ?? "http://localhost:8274",
        changeOrigin: true,
      },
    },
  },
});
