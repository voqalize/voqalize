/**
 * Screenshots of every route at desktop (1440×900) and phone (390×844), plus
 * mid-flow states driven by Stage moves through `?debug=1` and
 * `window.__bankMove(id, args)` (the same path a brain's move takes).
 *
 *   pnpm dev --port 5404 &
 *   node scripts/screenshots.mjs [origin] [outDir] [only-name-substring]
 *
 * origin defaults to http://localhost:5404, outDir to ./screenshots (gitignored).
 */
import { existsSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const origin = process.argv[2] ?? "http://localhost:5404";
const out = resolve(process.argv[3] ?? join(here, "..", "screenshots"));
const only = process.argv[4];
const base = `${origin}/demos/bank`;

const settle = (page, ms = 600) => page.waitForTimeout(ms);
/** Run a move through Stage, as the brain would, and wait for its rings. */
async function move(page, id, args, wait = 900) {
  const r = await page.evaluate(([i, a]) => window.__bankMove(i, a), [id, args]);
  if (r && r.outcome && r.outcome !== "applied") console.log(`   ${id}: ${r.outcome} ${r.detail ?? ""} ${JSON.stringify(r.refused ?? [])}`);
  if (r && r.error) console.log(`   ${id}: ${r.error}`);
  await settle(page, wait);
  return r;
}
async function closeConsole(page) {
  // A click from inside the page: a sheet may be over the console.
  await page.evaluate(() => document.querySelector('.debug [aria-label="Close move console"]')?.click());
}

/** Last calendar month as days_ago bounds. */
const LAST_MONTH = (() => {
  const t = new Date();
  t.setHours(0, 0, 0, 0);
  const first = new Date(t.getFullYear(), t.getMonth() - 1, 1);
  const last = new Date(t.getFullYear(), t.getMonth(), 0);
  const d = (x) => Math.round((t - x) / 86400000);
  return { from_days_ago: d(first), to_days_ago: d(last) };
})();

const SHOTS = [
  // ── Routes ──
  { name: "home", path: "/", full: true },
  { name: "home-signed-in", path: "/", signedIn: true },
  { name: "login", path: "/login" },
  { name: "app-guard", path: "/app/bills" },
  { name: "open-account", path: "/open-account" },
  { name: "cards", path: "/cards", full: true },
  { name: "cards-signed-in", path: "/cards", signedIn: true },
  { name: "card-detail", path: "/cards/voyage", full: true },
  { name: "cards-compare", path: "/cards/compare", full: true },
  { name: "cards-apply", path: "/cards/apply?card=daily" },
  { name: "cards-emi", path: "/cards/emi" },
  { name: "loans", path: "/loans", full: true },
  { name: "loan-home", path: "/loans/home", full: true },
  { name: "loan-gold", path: "/loans/gold" },
  { name: "loan-apply", path: "/loans/apply?type=personal" },

  // ── Mid-flow, by move ──
  {
    name: "flow-open-account-half",
    path: "/open-account?debug=1",
    run: async (page) => {
      for (const [field, value] of [
        ["full_name", "Priya Raghavan"],
        ["date_of_birth", "1993-04-18"],
        ["gender", "female"],
        ["mobile", "98450 12873"],
        ["email", "priya.r@example.com"],
        ["address_line", "Flat 4B, Lakeview Apartments, 12th Main, Indiranagar"],
        ["city", "Bengaluru"],
        ["state", "Karnataka"],
        ["pincode", "560038"],
        ["residence_type", "rented"],
        ["pan", "BQRPR4821K"],
        ["aadhaar", "4821 7765 3012"],
      ])
        await move(page, "form.fill", { form: "open_account", field, value }, 150);
      await move(page, "form.fill", { form: "open_account", field: "pan", value: "ABC123" }, 100);
      await page.mouse.click(5, 300);
      await settle(page, 400);
    },
  },
  {
    name: "flow-open-account-variant",
    path: "/open-account?debug=1",
    run: async (page) => {
      await move(page, "form.fill", { form: "open_account", field: "variant", value: "privilege" }, 1200);
    },
  },
  {
    name: "flow-cards-compare",
    path: "/cards?debug=1",
    run: async (page) => {
      await move(page, "cards.compare", { card_ids: ["voyage", "daily", "prism"], dining: 9000, online: 14000, groceries: 8000, travel: 18000, fuel: 2000, utilities: 6000, other: 7000 }, 1400);
    },
  },
  {
    name: "flow-emi-txn",
    path: "/?debug=1",
    signedIn: true,
    run: async (page) => {
      await move(page, "emi.plan", { txn_id: "T0184", tenure_months: 12 }, 1400);
    },
  },
  {
    name: "flow-loan-calc",
    path: "/?debug=1",
    run: async (page) => {
      await move(page, "loan.calc", { loan_type: "home", amount: 6000000, tenure_months: 240 }, 600);
      await move(page, "loan.eligibility", { loan_type: "home", monthly_income: 150000, existing_emis: 12000, tenure_months: 240 }, 1400);
    },
  },
  {
    name: "flow-loan-lead",
    path: "/loans/apply?type=home&debug=1",
    run: async (page) => {
      for (const [field, value] of [
        ["full_name", "Karthik Iyer"],
        ["mobile", "9840012345"],
        ["city", "Chennai"],
        ["employment", "salaried"],
        ["employer", "Sundaram Textiles Pvt Ltd"],
        ["monthly_income", "150000"],
        ["existing_emis", "12000"],
        ["amount", "6000000"],
        ["tenure_months", "240"],
        ["property_value", "8500000"],
        ["preferred_time", "evening"],
      ])
        await move(page, "form.fill", { form: "loan_apply", field, value }, 80);
      await move(page, "form.submit", { form: "loan_apply" }, 1600);
    },
  },
  {
    name: "flow-nav-signin",
    path: "/?debug=1",
    run: async (page) => {
      await move(page, "nav.open", { screen: "credit_card" }, 1200);
    },
  },
  // The banking app's moves (its performers, through the same Stage).
  {
    name: "flow-txn-find",
    path: "/app?debug=1",
    signedIn: true,
    run: async (page) => {
      await move(page, "txn.find", { category: "food", ...LAST_MONTH, label: "Food last month" }, 1600);
    },
  },
  {
    name: "flow-txn-open",
    path: "/app/transactions?debug=1",
    signedIn: true,
    run: async (page) => {
      await move(page, "txn.open", { txn_id: "T0197" }, 1400);
    },
  },
  {
    name: "flow-confirm-block",
    path: "/app/cards/debit?debug=1",
    signedIn: true,
    run: async (page) => {
      await move(page, "confirm.ask", { action_id: "A1", kind: "card_block", card: "debit" }, 1400);
    },
  },
  {
    name: "call-tile",
    path: "/cards?debug=1",
    run: async (page) => {
      await page.click('[data-fake="connect"]');
      await page.click('[data-fake="speak"]');
      await settle(page, 900);
    },
  },
];

await mkdir(out, { recursive: true });
const shell = join(homedir(), ".cache/ms-playwright/chromium_headless_shell-1248");
const fallback = join(homedir(), ".cache/ms-playwright/chromium-1248/chrome-linux64/chrome");
let browser;
try {
  browser = await chromium.launch();
} catch (err) {
  if (!existsSync(fallback)) throw err;
  console.log(`(headless shell missing${existsSync(shell) ? "" : ` at ${shell}`}; using ${fallback})`);
  browser = await chromium.launch({ executablePath: fallback });
}
for (const width of [1440, 390]) {
  const ctx = await browser.newContext({
    viewport: { width, height: width > 600 ? 900 : 844 },
    deviceScaleFactor: width > 600 ? 1 : 2,
    isMobile: width < 600,
    hasTouch: width < 600,
  });
  for (const shot of SHOTS) {
    if (only && !shot.name.includes(only)) continue;
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    if (shot.signedIn) await page.addInitScript(() => sessionStorage.setItem("anvaya-signed-in", "1"));
    await page.goto(`${base}${shot.path}`, { waitUntil: "networkidle" });
    await settle(page);
    if (shot.run) await shot.run(page);
    await closeConsole(page);
    if (shot.full) {
      const h = await page.evaluate(() => document.body.scrollHeight);
      for (let y = 0; y < h; y += 700) {
        await page.evaluate((top) => window.scrollTo(0, top), y);
        await page.waitForTimeout(60);
      }
      if (!shot.run) await page.evaluate(() => window.scrollTo(0, 0));
      await settle(page, 400);
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const file = join(out, `${shot.name}-${width}.png`);
    await page.screenshot({ path: file, fullPage: shot.full ?? false });
    console.log(`${file}${overflow > 0 ? `  OVERFLOW ${overflow}px` : ""}${errors.length ? `  ERRORS: ${errors.join(" | ").slice(0, 400)}` : ""}`);
    await page.close();
  }
  await ctx.close();
}
await browser.close();
