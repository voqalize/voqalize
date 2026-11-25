/**
 * A file at every static route, so deep links and refreshes work on static
 * hosting. The apex serves static files first and answers anything else with
 * ITS OWN index.html (the marketing home page), so a route with no file behind
 * it would show the wrong site on reload. After `vite build`, this writes a
 * copy of dist/index.html at each known route with that page's <title>:
 * /shop, /shop/<dept>, /shop/<dept>/<type> (from the catalogue's departments),
 * /compare, /wishlist, /bag, /checkout, /orders, /returns, /gifts, /kiosk, /about.
 *
 * Product pages are NOT written one by one (4,623 of them). Instead one file
 * sits at /p/index.html, and the product link that must survive a cold open (a
 * kiosk QR code, a shared link: `shareUrl` in src/data/catalog.ts) is
 * /p/?id=<id>; the app's not-found route moves it on to /p/<id>. A pretty
 * /p/<id> works for every in-app visit; reloading one on static hosting falls
 * through to the apex, which is the known limit.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "..", "dist");
const catalog = JSON.parse(await readFile(join(here, "..", "..", "data", "catalog.json"), "utf8"));
const shell = await readFile(join(dist, "index.html"), "utf8");
const BRAND = "Fashio";
const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const typeLabel = (t) => catalog.types[t]?.label ?? t;

const routes = [
  ["shop", "Shop everything"],
  ["compare", "Compare"],
  ["wishlist", "Wishlist"],
  ["bag", "Bag"],
  ["checkout", "Checkout"],
  ["orders", "Your orders"],
  ["returns", "Returns"],
  ["gifts", "Gift finder"],
  ["kiosk", "Store kiosk"],
  ["about", "About Fashio"],
  ["p", "Product"],
];
const seen = new Set();
for (const d of catalog.departments) {
  routes.push([`shop/${d.id}`, d.label]);
  for (const t of d.sections.flatMap((s) => s.types)) {
    if (seen.has(`${d.id}/${t}`)) continue;
    seen.add(`${d.id}/${t}`);
    routes.push([`shop/${d.id}/${t}`, `${d.label}: ${typeLabel(t)}`]);
  }
}
for (const d of ["boys", "girls"]) routes.push([`shop/${d}`, d === "boys" ? "Boys" : "Girls"]);

for (const [path, title] of routes) {
  const html = shell.replace(/<title>[^<]*<\/title>/, `<title>${escape(`${title} · ${BRAND}`)}</title>`);
  const target = join(dist, path, "index.html");
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
}
console.log(`route-shells: ${routes.length} routes`);
