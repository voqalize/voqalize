/**
 * A file at every route, so deep links and refreshes work on static hosting.
 *
 * The site routes on the path (/demos/insurance/quote/car, /my-policies/car-2026…).
 * The apex's hosting serves static files first and answers anything else with
 * ITS OWN index.html, so without a file at each route a refreshed page would
 * show the wrong site. After `vite build`, this writes a copy of dist/index.html
 * at each known route, with that page's own <title>.
 */
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const dist = join(app, "dist");
const data = join(app, "..", "data");
const products = JSON.parse(await readFile(join(data, "products.json"), "utf8")).products;
const shell = await readFile(join(dist, "index.html"), "utf8");

let policyFiles = [];
try {
  policyFiles = (await readdir(join(data, "policies"))).filter((n) => n.endsWith(".json"));
} catch {
  /* no policies yet */
}
const policies = await Promise.all(policyFiles.map(async (n) => JSON.parse(await readFile(join(data, "policies", n), "utf8"))));

const SITE = "Chhatri Insurance";
const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const routes = [
  ["quote", "Get a quote"],
  ["my-policies", "My policies"],
  ["claim", "Make a claim"],
  ["claim/submitted", "Claim submitted"],
];
for (const p of products) {
  routes.push([`insurance/${p.id}`, p.name]);
  routes.push([`quote/${p.id}`, `${p.name} quote`]);
}
for (const p of policies) routes.push([`my-policies/${p.id}`, `${p.title} ${p.policy_number}`]);

let written = 0;
for (const [path, title] of routes) {
  const html = shell.replace(/<title>[^<]*<\/title>/, `<title>${escape(`${title} — ${SITE}`)}</title>`);
  const target = join(dist, path, "index.html");
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
  written += 1;
}
console.log(`route-shells: ${written} routes`);
