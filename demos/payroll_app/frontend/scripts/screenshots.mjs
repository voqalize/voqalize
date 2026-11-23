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
  ["run-jan", "/payroll/PR-2026-01"],
  ["payroll-runs", "/payroll"],
  ["payslips", "/payslips"],
  ["tax", "/tax"],
  ["settings", "/settings"],
  ["employee-ravi", "/employees/BB-1030"],
  ["employee-new", "/employees/new"],
  ["me-ravi", "/me/BB-1030/payslips"],
];

const SAMPLE = join(here, "..", "..", "data", "employees_import.csv");
/** The wizard up to a step, the way the admin does it: presets by button, the file by Import file. */
async function wizardTo(page, step) {
  const order = ["company", "structure", "import", "leave", "test_run", "done"];
  const upto = order.indexOf(step);
  await page.click('[data-presets="company"]');
  if (upto >= 1) {
    await run(page, "setup.step", { step: "structure" });
    if (upto >= 2) await page.click('[data-presets="structure"]');
  }
  if (upto >= 2) {
    await run(page, "setup.step", { step: "import" });
    if (upto >= 3) await page.setInputFiles("[data-import-input]", SAMPLE);
  }
  if (upto >= 3) {
    await run(page, "setup.step", { step: "leave" });
    if (upto >= 4) await page.click('[data-presets="leave"]');
  }
  if (upto >= 4) await run(page, "setup.test_run", {});
  if (upto >= 5) await run(page, "setup.step", { step: "done" });
  await page.waitForTimeout(500);
}
const wizardFlow = (name, step, extra) => ({
  name,
  path: "/welcome?debug=1",
  run: async (page) => {
    await closeDebug(page);
    await wizardTo(page, step);
    if (extra) await extra(page);
    await page.evaluate(() => window.scrollTo({ top: 0 }));
    await page.waitForTimeout(300);
  },
});

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
  wizardFlow("setup-1-company", "company"),
  wizardFlow("setup-2-structure-empty", "structure"),
  {
    name: "setup-2-structure-asked",
    path: "/welcome?debug=1",
    run: async (page) => {
      await closeDebug(page);
      await page.click('[data-presets="company"]');
      await run(page, "setup.step", { step: "structure" });
      await page.evaluate(() => window.__tkFakeCall?.("speaking"));
      await page.waitForTimeout(600);
    },
  },
  wizardFlow("setup-2-structure-defaults", "import", async (page) => run(page, "setup.step", { step: "structure" })),
  {
    name: "setup-3-import-example",
    path: "/welcome?debug=1",
    run: async (page) => {
      await closeDebug(page);
      await page.click('[data-presets="company"]');
      await run(page, "setup.step", { step: "import" });
      await page.evaluate(() => window.__tkFakeCall?.("speaking"));
      void run(page, "app.show", { thing: "Import file" });
      await page.waitForTimeout(900);
    },
  },
  wizardFlow("setup-3-import-done", "leave", async (page) => run(page, "setup.step", { step: "import" })),
  {
    name: "setup-4-leave-asked",
    path: "/welcome?debug=1",
    run: async (page) => {
      await closeDebug(page);
      await run(page, "setup.step", { step: "leave" });
      await page.waitForTimeout(400);
    },
  },
  wizardFlow("setup-4-leave-defaults", "test_run", async (page) => run(page, "setup.step", { step: "leave" })),
  wizardFlow("setup-5-test-run", "test_run"),
  wizardFlow("setup-6-done", "done"),
  {
    name: "approval-question",
    path: "/leave?tab=requests&debug=1",
    run: async (page) => {
      await closeDebug(page);
      await page.evaluate(() => window.__tkFakeCall?.("speaking"));
      void run(page, "app.show", { thing: "Pending requests" });
      await page.waitForTimeout(900);
    },
  },
  {
    name: "approval-claim-question",
    path: "/reimbursements?debug=1",
    run: async (page) => {
      await closeDebug(page);
      await page.evaluate(() => window.__tkFakeCall?.("speaking"));
      await run(page, "claim.open", { claim_id: "RB-3108" });
      await page.waitForTimeout(600);
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
