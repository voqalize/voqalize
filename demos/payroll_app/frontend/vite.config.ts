import react from "@vitejs/plugin-react";
import { type Connect, type Plugin, defineConfig } from "vite";
import { avatarRuntime } from "../../shared/avatar-runtime.mjs";
import { noDaily } from "../../shared/no-daily.mjs";

// Paynora is the product itself, signed in as an HR admin, with real URLs
// (/demos/payroll_app/payslips/BB-1030/2026-01, /tax/regime/BB-1007…). The app
// routes on the path (BrowserRouter with this base), and
// scripts/route-shells.mjs writes a copy of index.html at every route after the
// build, so a deep link or a refresh on static hosting finds a file of its own.
// The dev port is passed on the command line (`pnpm dev --port 5403`), never
// written here.
const BASE = "/demos/payroll_app/";

/**
 * `/demos/payroll_app` (no slash, any query) answers a 302 to
 * `/demos/payroll_app/`, in dev and in preview, so that address loads on a
 * reload. The app itself never writes it (see `withSlash` in src/state/nav.ts).
 */
function baseSlash(): Plugin {
  const bare = BASE.replace(/\/$/, "");
  const redirect: Connect.NextHandleFunction = (req, res, next) => {
    const url = req.url ?? "";
    const [path, query] = url.split(/\?(.*)/s, 2);
    if (path !== bare) return next();
    res.statusCode = 302;
    res.setHeader("Location", `${BASE}${query ? `?${query}` : ""}`);
    res.end();
  };
  return {
    name: "payroll-base-slash",
    configureServer: (server) => void server.middlewares.use(redirect),
    configurePreviewServer: (server) => void server.middlewares.use(redirect),
  };
}

export default defineConfig({
  base: BASE,
  publicDir: "../../public",
  plugins: [react(), avatarRuntime(), noDaily(), baseSlash()],
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
