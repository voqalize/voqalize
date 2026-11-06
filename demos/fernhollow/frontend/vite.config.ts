import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { type Plugin, defineConfig } from "vite";
import { avatarRuntime } from "../../shared/avatar-runtime.mjs";
import { noDaily } from "../../shared/no-daily.mjs";

// Fernhollow is a store, so it has real URLs: /demos/fernhollow/product/<id>,
// /room/<room>, /journal/<slug>… The app routes on the path (BrowserRouter with
// this base) and `scripts/route-shells.mjs` writes a copy of index.html at every
// route after the build, so a deep link or a refresh on static hosting finds a
// file of its own rather than the apex's catch-all.
const BASE = "/demos/fernhollow/";

const CATALOG = fileURLToPath(new URL("../data/catalog.json", import.meta.url));
// Each product's materials, colours and styles as the brain reads them, so
// the listing filters by the same words Emily asks about.
const ATTRIBUTES = fileURLToPath(new URL("../backend/data/attributes.json", import.meta.url));
const VIRTUAL = "virtual:catalog";

/**
 * `virtual:catalog` — data/catalog.json with only the fields the store renders.
 * The source carries CDN urls, alt prompts, tags and a duplicated description;
 * none of them reach a page, so none of them ship.
 */
function slimCatalog(): Plugin {
  return {
    name: "fernhollow-catalog",
    resolveId: (id) => (id === VIRTUAL ? `\0${VIRTUAL}` : null),
    load(id) {
      if (id !== `\0${VIRTUAL}`) return null;
      this.addWatchFile(CATALOG);
      this.addWatchFile(ATTRIBUTES);
      const raw = JSON.parse(readFileSync(CATALOG, "utf8"));
      const attrs: Record<string, Record<string, [string, string][]>> = JSON.parse(readFileSync(ATTRIBUTES, "utf8"));
      const words = (id: string, kind: string) => [...new Set((attrs[id]?.[kind] ?? []).map(([w]) => w))];
      const products = raw.products.map((p: Record<string, any>) => ({
        id: p.id,
        title: p.title,
        category: p.category,
        categorySlug: p.categorySlug,
        room: p.room,
        collections: p.collections,
        intro: p.intro,
        highlights: p.highlights,
        priceMin: p.priceMin,
        priceMax: p.priceMax,
        onSale: p.onSale,
        options: p.options,
        variants: p.variants.map((v: Record<string, any>) => ({
          id: v.id,
          title: v.title,
          options: v.options,
          price: v.price,
          compareAtPrice: v.compareAtPrice ?? null,
        })),
        images: p.images.map((i: Record<string, any>) => i.file),
        taste: { materials: words(p.id, "materials"), colours: words(p.id, "colours"), styles: words(p.id, "styles") },
      }));
      const slim = { store: raw.store, rooms: raw.rooms, categories: raw.categories, products };
      return `export default JSON.parse(${JSON.stringify(JSON.stringify(slim))});`;
    },
  };
}

export default defineConfig({
  base: BASE,
  // This app's own public/ holds the product images (scripts/images.mjs writes
  // them, and copies the gallery favicon from ../../public beside them).
  publicDir: "public",
  plugins: [react(), slimCatalog(), avatarRuntime(), noDaily()],
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("virtual:catalog")) return "catalog";
          if (id.includes("node_modules/react") || id.includes("react-router")) return "react";
        },
      },
    },
  },
  server: {
    allowedHosts: [".local.voqalize.com"],
    // Journal and info pages live in ../content, outside this app.
    fs: { allow: ["..", "../../shared"] },
    proxy: {
      "/api": {
        target: process.env.VOQALIZE_API_TARGET ?? "http://localhost:8274",
        changeOrigin: true,
      },
    },
  },
  preview: { port: 4317 },
});
