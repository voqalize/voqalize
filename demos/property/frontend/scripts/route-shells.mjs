/**
 * A file at every route, so deep links and refreshes work on static hosting:
 * the apex serves static files first and answers anything else with its own
 * index.html. After `vite build`, this writes a copy of dist/index.html at
 * each known route (/listing/<id>, /project/<id>, …) with that page's title.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "..", "dist");
const data = JSON.parse(await readFile(join(here, "..", "..", "data", "homes.json"), "utf8"));
const shell = await readFile(join(dist, "index.html"), "utf8");
const BRAND = data.brand.name;
const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const routes = [
  ["listings", "Find a home"],
  ["compare", "Compare homes"],
  ["shortlist", "Shortlist"],
  ["visits", "My site visits"],
];
for (const l of data.listings) routes.push([`listing/${l.id}`, `${l.title}, ${l.locality}`]);
for (const p of data.projects) routes.push([`project/${p.id}`, `${p.name}, ${p.locality}`, p.pitch]);

for (const [path, title, description] of routes) {
  let html = shell.replace(/<title>[^<]*<\/title>/, `<title>${escape(`${title} · ${BRAND}`)}</title>`);
  if (description) html = html.replace(/<meta name="description" content="[^"]*"/, `<meta name="description" content="${escape(description)}"`);
  const target = join(dist, path, "index.html");
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
}
console.log(`route-shells: ${routes.length} routes`);
