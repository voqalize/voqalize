/**
 * A file at every route, so deep links and refreshes work on static hosting.
 *
 * The bank routes on the path (/demos/bank/cards/voyage, /demos/bank/app/bills…).
 * Static hosting serves files first and answers anything else with its own
 * index.html, so after `vite build` this writes a copy of dist/index.html at each
 * route in CONTRACT.md's table, with that page's own <title>. The app is the same
 * bundle everywhere; only the shell differs. Query-string routes (?card=, ?txn=,
 * ?type=) share their path's file.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const dist = join(app, "dist");
const products = JSON.parse(await readFile(join(app, "..", "data", "products.json"), "utf8"));
const shell = await readFile(join(dist, "index.html"), "utf8");
const BANK = products.brand.name;

const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const routes = [
  ["login", "Sign in"],
  ["app", "My banking"],
  ["app/accounts/sb", "Savings account"],
  ["app/accounts/ca", "Current account"],
  ["app/transactions", "Transactions"],
  ["app/insights", "Spending insights"],
  ["app/cards", "Your cards"],
  ["app/cards/debit", "Debit card"],
  ["app/cards/credit", "Credit card"],
  ["app/payments", "Payments"],
  ["app/bills", "Bills"],
  ["app/deposits", "Fixed deposits"],
  ["app/statements", "Statements"],
  ["app/offers", "Offers"],
  ["open-account", "Open a savings account"],
  ["cards", "Credit cards"],
  ["cards/compare", "Compare credit cards"],
  ["cards/apply", "Apply for a credit card"],
  ["cards/emi", "EMI planner"],
  ["loans", "Loans"],
  ["loans/apply", "Apply for a loan"],
];
for (const c of products.credit_cards) routes.push([`cards/${c.id}`, c.name, c.highlights.join(". ")]);
for (const l of products.loans) routes.push([`loans/${l.id}`, l.name, l.highlights.join(". ")]);

let written = 0;
for (const [path, title, description] of routes) {
  let html = shell.replace(/<title>[^<]*<\/title>/, `<title>${escape(`${title} — ${BANK}`)}</title>`);
  if (description) html = html.replace(/<meta name="description" content="[^"]*"/, `<meta name="description" content="${escape(description)}"`);
  const target = join(dist, path, "index.html");
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
  written += 1;
}
console.log(`route-shells: ${written} routes`);
