/**
 * A file at every route, so deep links and refreshes work on static hosting.
 *
 * Paynora routes on the path (/demos/payroll_app/payslips/BB-1030/2026-01…).
 * The apex's hosting serves static files first and answers anything else with
 * ITS OWN index.html, so without a file at each route a refreshed screen would
 * show the wrong site. After `vite build`, this writes a copy of
 * dist/index.html at each known route, with that screen's own <title>.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const dist = join(app, "dist");
const company = JSON.parse(await readFile(join(app, "..", "data", "company.json"), "utf8"));
const shell = await readFile(join(dist, "index.html"), "utf8");

const escape = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const MONTHS = ["2025-11", "2025-12", "2026-01", "2026-02"];

const routes = [
  ["welcome", "Setup"],
  ["employees", "Employees"],
  ["employees/new", "Add employee"],
  ["payroll", "Payroll runs"],
  ["payslips", "Payslips"],
  ["leave", "Leave"],
  ["reimbursements", "Reimbursements"],
  ["tax", "Tax"],
  ["settings", "Settings"],
  ["help", "Help"],
];
for (const r of company.payroll_runs) routes.push([`payroll/${r.id}`, `${r.label} payroll run`]);
for (const e of company.employees) {
  routes.push([`employees/${e.id}`, e.name]);
  routes.push([`tax/regime/${e.id}`, `${e.name}, regime comparison`]);
  for (const tab of ["payslips", "tax", "declarations", "leave"]) routes.push([`me/${e.id}/${tab}`, `Employee view: ${e.name}`]);
  for (const m of MONTHS) if (company.payslips[e.id]?.some((s) => s.month === m)) routes.push([`payslips/${e.id}/${m}`, `${e.name}, payslip`]);
}

let written = 0;
for (const [path, title] of routes) {
  const html = shell.replace(/<title>[^<]*<\/title>/, `<title>${escape(`${title}, Paynora`)}</title>`);
  const target = join(dist, path, "index.html");
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
  written += 1;
}
console.log(`route-shells: ${written} routes`);
