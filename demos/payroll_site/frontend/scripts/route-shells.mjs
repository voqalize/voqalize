/**
 * A file at every route, so deep links and refreshes work on static hosting.
 *
 * The site routes on the path (/demos/payroll_site/pricing, /modules/<id>…).
 * The apex's hosting serves static files first and answers anything else with
 * its own index.html, so without dist/pricing/index.html a refreshed pricing
 * page would show the wrong site. After `vite build`, this writes a copy of
 * dist/index.html at each route, with that page's own <title>.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const dist = join(app, "dist");
const product = JSON.parse(await readFile(join(app, "..", "data", "product.json"), "utf8"));
const site = JSON.parse(await readFile(join(app, "..", "content", "site.json"), "utf8"));
const shell = await readFile(join(dist, "index.html"), "utf8");
const brand = product.brand.name;

const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const routes = Object.entries(site.pages)
  .filter(([path]) => path !== "/")
  .map(([path, title]) => [path.slice(1), title]);
for (const m of product.modules) routes.push([`modules/${m.id}`, m.name]);

for (const [route, title] of routes) {
  const html = shell.replace(/<title>[^<]*<\/title>/, `<title>${escape(`${title} — ${brand}`)}</title>`);
  const dir = join(dist, route);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, "index.html"), html);
}
console.log(`route shells: ${routes.length} routes`);
