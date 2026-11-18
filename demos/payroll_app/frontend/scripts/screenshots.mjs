/**
 * Screenshots of every landing at desktop (1440x900) and phone (390x844), and
 * mid-flow states driven through `?debug=1` and `window.__tkRun`, against a
 * running `pnpm preview --port 5403` (or dev).
 *
 *   node scripts/screenshots.mjs [baseUrl] [outDir] [only-name-substring]
 */
import { existsSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const origin = process.argv[2] ?? "http://localhost:5403";
const out = process.argv[3] ?? join(here, "..", "screenshots");
const only = process.argv[4];
const base = `${origin}/demos/payroll_app`;
const FALLBACK = "/home/samkeet/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";

const LANDINGS = [
  ["welcome", "/welcome"],
  ["dashboard", "/"],
  ["help", "/help"],
  ["regime-kavitha", "/tax/regime/BB-1007"],
  ["payslip-ravi-compare", "/payslips/BB-1030/2026-01?against=2025-12"],
  ["leave", "/leave"],
  ["reimbursements", "/reimbursements"],
  ["employees", "/employees"],
  ["run-feb", "/payroll/PR-2026-02"],
  ["me-ravi", "/me/BB-1030/payslips"],
];

const run = (page, id, args) => page.evaluate(([i, a]) => window.__tkRun(i, a), [id, args]).catch(() => null);
const closeDebug = (page) => page.click('[aria-label="Close move console"]').catch(() => {});

const FLOWS = [
  {
    name: "flow-ravi-tds-ring",
    path: "/payslips/BB-1030/2026-01?against=2025-12&debug=1",
    run: async (page) => {
      await closeDebug(page);
      void run(page, "app.show", { thing: "TDS" });
      await page.waitForTimeout(900);
    },
  },
  {
    name: "flow-kavitha-old-slabs-ring",
    path: "/tax/regime/BB-1007?debug=1",
    run: async (page) => {
      await closeDebug(page);
      void run(page, "app.show", { thing: "Old regime slabs" });
      await page.waitForTimeout(900);
    },
  },
  {
    name: "flow-setup-import",
    path: "/welcome?debug=1",
    run: async (page) => {
      await closeDebug(page);
      await run(page, "setup.step", { step: "company" });
      for (const [field, value] of [
        ["company_name", "Banyan & Bay Foods"],
        ["legal_name", "Banyan & Bay Foods Pvt. Ltd."],
        ["pan", "AAKCB7713Q"],
        ["tan", "BLRB09412E"],
        ["basic_pct", "40"],
        ["hra_metro_pct", "50"],
      ]) {
        await run(page, "setup.fill", { field, value });
      }
      await run(page, "setup.import", {});
      await page.waitForTimeout(1200);
    },
  },
  {
    name: "flow-leave-approve-ring",
    path: "/leave?debug=1",
    run: async (page) => {
      await closeDebug(page);
      void run(page, "leave.decide", { request_id: "LV-2412", decision: "approve" });
      await page.waitForTimeout(750);
    },
  },
  {
    name: "flow-leave-approve-done",
    path: "/leave?debug=1",
    run: async (page) => {
      await closeDebug(page);
      await run(page, "leave.decide", { request_id: "LV-2412", decision: "approve" });
      await page.waitForTimeout(400);
    },
  },
  {
    name: "flow-debug-console",
    path: "/?debug=1",
    desktopOnly: true,
    run: async (page) => {
      await page.waitForTimeout(300);
    },
  },
];

const VIEWPORTS = [
  ["desktop", { width: 1440, height: 900 }],
  ["phone", { width: 390, height: 844 }],
];

await mkdir(out, { recursive: true });
let browser;
try {
  browser = await chromium.launch();
} catch {
  browser = await chromium.launch({ executablePath: existsSync(FALLBACK) ? FALLBACK : undefined });
}
for (const [vp, size] of VIEWPORTS) {
  const ctx = await browser.newContext({ viewport: size, deviceScaleFactor: vp === "phone" ? 2 : 1 });
  for (const [name, path] of LANDINGS) {
    if (only && !name.includes(only)) continue;
    const page = await ctx.newPage();
    await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(400);
    await page.screenshot({ path: join(out, `${name}-${vp}.png`), fullPage: vp === "phone" ? false : false });
    await page.close();
  }
  for (const f of FLOWS) {
    if (only && !f.name.includes(only)) continue;
    if (f.desktopOnly && vp !== "desktop") continue;
    const c = await browser.newContext({ viewport: size, deviceScaleFactor: vp === "phone" ? 2 : 1 });
    const page = await c.newPage();
    page.on("pageerror", (e) => console.error(`${f.name}: ${e.message}`));
    await page.goto(`${base}${f.path}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(300);
    await f.run(page);
    await page.screenshot({ path: join(out, `${f.name}-${vp}.png`) });
    await c.close();
  }
  await ctx.close();
}
await browser.close();
console.log(`screenshots in ${out}`);
