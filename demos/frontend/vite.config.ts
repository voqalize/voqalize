import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// One Rollup entry per HTML page, derived from the shared manifest so adding a
// demo (a manifest entry + its `{name}.html`) never touches this config.
interface Manifest {
  demos: { name: string }[];
}
const manifest = JSON.parse(
  readFileSync(new URL("../manifest.json", import.meta.url), "utf-8"),
) as Manifest;

const input: Record<string, string> = {
  index: fileURLToPath(new URL("./index.html", import.meta.url)),
};
for (const d of manifest.demos) {
  input[d.name] = fileURLToPath(new URL(`./${d.name}.html`, import.meta.url));
}

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: { input },
  },
  server: {
    port: 5750,
    // The manifest lives one level up (the shared spine); allow the dev server to
    // read it, and proxy the session-bootstrap API to the control plane.
    fs: { allow: [".."] },
    proxy: {
      "/api": { target: "http://localhost:8274", changeOrigin: true },
    },
  },
});
