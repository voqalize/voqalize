/**
 * A file at every route, so deep links and refreshes work on static hosting.
 *
 * The clinic routes on the path (/demos/dental/book, /my-appointments). The
 * apex's hosting serves static files first and answers anything else with its
 * own index.html, so after `vite build` this writes a copy of dist/index.html
 * at each route, with that page's own <title>.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "..", "dist");
const shell = await readFile(join(dist, "index.html"), "utf8");
const CLINIC = "Dantika Dental Studio";
const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const routes = [
  ["book", "Book an appointment", "See each dentist's free times and book a check-up, procedure or scan."],
  ["my-appointments", "My appointments", "Sign in with your mobile to see, move or cancel your appointments."],
];
for (const [path, title, description] of routes) {
  let html = shell.replace(/<title>[^<]*<\/title>/, `<title>${escape(`${title} — ${CLINIC}`)}</title>`);
  html = html.replace(/<meta name="description" content="[^"]*"/, `<meta name="description" content="${escape(description)}"`);
  const target = join(dist, path, "index.html");
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
}
console.log(`route-shells: ${routes.length} routes`);
