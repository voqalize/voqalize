import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The landing page is the demos index, served at the site root `/`. It reads the
// shared demos directory (../../../manifest.json), so the dev server needs read
// access one level above its own root; the production build bundles the JSON in.
export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    port: 5750,
    fs: { allow: ["../../.."] },
  },
});
