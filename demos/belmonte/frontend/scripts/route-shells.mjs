/**
 * A file at every route, so deep links and refreshes work on static hosting:
 * the apex serves static files first and answers anything else with its own
 * index.html. After `vite build` this writes a copy of dist/index.html at each
 * route the app has, with that page's own <title>.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const shell = await readFile(join(dist, "index.html"), "utf8");
const routes = [
  ["dining", "In-room dining"],
  ["bar", "Drinks"],
  ["spa", "Spa"],
  ["activities", "Activities"],
  ["meetings", "Meeting rooms"],
  ["requests", "Requests"],
  ["visitors", "Visitors"],
  ["stay", "Your stay"],
  ["stay/check-in", "Check-in"],
  ["stay/check-out", "Check-out"],
  ["info", "Hotel information"],
];
for (const [path, title] of routes) {
  await mkdir(join(dist, path), { recursive: true });
  const html = shell.replace(/<title>[^<]*<\/title>/, `<title>${title} · Hotel Belmonte</title>`);
  await writeFile(join(dist, path, "index.html"), html);
}
console.log(`route shells: ${routes.map(([p]) => p).join(", ")}`);
