/**
 * A file at every route, so deep links and refreshes work on static hosting.
 *
 * The site routes on the path (/demos/university/programs/<id>, /apply…). The
 * apex's hosting serves static files first and answers anything else with its
 * own index.html, so without a file at each route a refreshed page would show
 * the wrong site. After `vite build`, this writes a copy of dist/index.html at
 * each known route, with that page's own <title>.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const dist = join(app, "dist");
const catalogue = JSON.parse(await readFile(join(app, "..", "data", "catalogue.json"), "utf8"));
const shell = await readFile(join(dist, "index.html"), "utf8");

const SITE = "Anvaya University";
const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const routes = [
  ["programs", "Find your programme"],
  ["schools", "Our schools"],
  ["admissions", "Admissions 2027"],
  ["scholarships", "Scholarships"],
  ["campus-life", "Campus life"],
  ["apply", "Apply for 2027"],
];
for (const s of catalogue.schools) routes.push([`schools/${s.id}`, s.name, s.blurb]);
for (const p of catalogue.programs) routes.push([`programs/${p.id}`, p.name, `${p.name}: ${p.eligibility.needs}.`]);

let written = 0;
for (const [path, title, description] of routes) {
  let html = shell.replace(/<title>[^<]*<\/title>/, `<title>${escape(`${title} | ${SITE}`)}</title>`);
  if (description) html = html.replace(/<meta name="description" content="[^"]*"/, `<meta name="description" content="${escape(description)}"`);
  const target = join(dist, path, "index.html");
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
  written += 1;
}
console.log(`route-shells: ${written} routes`);
