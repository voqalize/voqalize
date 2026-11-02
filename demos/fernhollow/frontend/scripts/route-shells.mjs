/**
 * A file at every route, so deep links and refreshes work on static hosting.
 *
 * The store routes on the path (/demos/fernhollow/product/<id>, /room/<room>…).
 * The apex's Firebase Hosting serves static files first and answers anything
 * else with ITS OWN index.html (the marketing home page) — so without a file
 * at /demos/fernhollow/product/<id>/index.html a refreshed product page would
 * show the wrong site. After `vite build`, this writes a copy of dist/index.html
 * at each known route, with that page's own <title>. The app is the same
 * bundle everywhere; only the shell differs.
 */
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const dist = join(app, "dist");
const content = join(app, "..", "content");
const catalog = JSON.parse(await readFile(join(app, "..", "data", "catalog.json"), "utf8"));
const shell = await readFile(join(dist, "index.html"), "utf8");

const STORE = "Fernhollow";
const ROOM_NAMES = {
  living: "Living room",
  dining: "Dining",
  bedroom: "Bedroom",
  "home-office": "Home office",
  bath: "Bath",
  kitchen: "Kitchen",
  decor: "Decor",
};

const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

async function frontmatter(dir) {
  let names = [];
  try {
    names = (await readdir(dir)).filter((n) => n.endsWith(".md") && !n.startsWith("_"));
  } catch {
    return [];
  }
  return Promise.all(
    names.map(async (n) => {
      const raw = await readFile(join(dir, n), "utf8");
      const m = /^---\r?\n([\s\S]*?)\r?\n---/.exec(raw);
      const get = (k) => {
        const line = m?.[1].split(/\r?\n/).find((l) => l.startsWith(`${k}:`));
        return line ? line.slice(k.length + 1).trim().replace(/^["']|["']$/g, "") : "";
      };
      return { slug: get("slug") || n.replace(/\.md$/, ""), title: get("title"), dek: get("dek") };
    }),
  );
}

const routes = [
  ["shop", "All pieces"],
  ["sale", "Sale"],
  ["search", "Search"],
  ["picks", "Picked for you"],
  ["board", "Plan a room"],
  ["compare", "Compare"],
  ["cart", "Cart"],
  ["checkout", "Checkout"],
  ["checkout/confirmation", "Order placed"],
  ["journal", "Journal"],
  ["contact", "Contact"],
];
for (const r of catalog.rooms) routes.push([`room/${r}`, ROOM_NAMES[r] ?? r]);
for (const c of catalog.categories) routes.push([`category/${c.slug}`, c.name]);
for (const p of catalog.products) routes.push([`product/${p.id}`, p.title, p.intro]);
for (const a of await frontmatter(join(content, "journal"))) routes.push([`journal/${a.slug}`, a.title, a.dek]);
for (const p of await frontmatter(join(content, "pages"))) {
  const path = p.slug === "about" || p.slug === "faq" ? p.slug : `policy/${p.slug}`;
  routes.push([path, p.title, p.dek]);
}

let written = 0;
for (const [path, title, description] of routes) {
  let html = shell.replace(/<title>[^<]*<\/title>/, `<title>${escape(`${title} — ${STORE}`)}</title>`);
  if (description) html = html.replace(/<meta name="description" content="[^"]*"/, `<meta name="description" content="${escape(description)}"`);
  const target = join(dist, path, "index.html");
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
  written += 1;
}
console.log(`route-shells: ${written} routes`);
