/**
 * Screenshots of every page, desktop (1440×900) and phone (390×844), plus
 * mid-flow states driven through the `?debug=1` move console. Needs the dev
 * server: `pnpm dev --port 5408`, then `node scripts/screenshots.mjs [outDir]`.
 */
import { existsSync, mkdirSync } from "node:fs";
import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://localhost:5408/demos/holidays";
const OUT = process.argv[2] ?? "screenshots";
mkdirSync(OUT, { recursive: true });
const CHROME = "/home/samkeet/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";
const browser = await chromium.launch(existsSync(CHROME) ? { executablePath: CHROME } : {});
const SIZES = { desktop: { width: 1440, height: 900 }, phone: { width: 390, height: 844 } };

async function page(size) {
  const ctx = await browser.newContext({ viewport: SIZES[size], deviceScaleFactor: size === "phone" ? 2 : 1 });
  const p = await ctx.newPage();
  p.on("pageerror", (e) => console.error("pageerror:", e.message));
  return p;
}
const move = async (p, id, n = 0) => {
  await p.locator(".debug-row", { has: p.locator("b", { hasText: new RegExp(`^${id.replace(".", "\\.")}$`) }) }).locator("button").nth(n).click();
  await p.waitForTimeout(400);
  await p.waitForFunction(() => window.__wlLast !== undefined, null, { timeout: 30000 });
};
async function shot(p, opts) {
  await p.evaluate(() => document.querySelector(".debug")?.setAttribute("style", "display:none"));
  await p.screenshot(opts);
  await p.evaluate(() => document.querySelector(".debug")?.removeAttribute("style"));
}
async function runMove(p, id, n = 0) {
  await p.evaluate(() => (window.__wlLast = undefined));
  await move(p, id, n);
  return p.evaluate(() => window.__wlLast);
}

for (const size of ["desktop", "phone"]) {
  const p = await page(size);
  await p.goto(`${BASE}/`);
  await p.waitForTimeout(800);
  await shot(p, { path: `${OUT}/home-${size}.png` });
  await shot(p, { path: `${OUT}/home-${size}-full.png`, fullPage: true });
  await p.goto(`${BASE}/plan`);
  await p.waitForTimeout(600);
  await shot(p, { path: `${OUT}/plan-${size}.png` });

  // Mid-flow, driven by the planner's own moves.
  await p.goto(`${BASE}/plan?debug=1`);
  await p.waitForTimeout(600);
  console.log(size, "brief", JSON.stringify(await runMove(p, "trip.brief", 0)));
  console.log(size, "flights", JSON.stringify(await runMove(p, "trip.flights", 1)));
  await p.waitForTimeout(1600);
  await p.evaluate(() => window.scrollTo(0, 0));
  await shot(p, { path: `${OUT}/flights-${size}.png` });
  console.log(size, "build", JSON.stringify(await runMove(p, "trip.build", 0)));
  await p.waitForTimeout(1500);
  await p.evaluate(() => window.scrollTo(0, 0));
  await shot(p, { path: `${OUT}/package-${size}.png` });
  await shot(p, { path: `${OUT}/package-${size}-full.png`, fullPage: true });
  console.log(size, "hotels beach", JSON.stringify(await runMove(p, "trip.hotels", 3)));
  console.log(size, "swap hotel", JSON.stringify(await runMove(p, "trip.hotel", 1)));
  await p.locator(".debug-row", { has: p.locator("b", { hasText: /^Call$/ }) }).locator("button").nth(2).click();
  await p.waitForTimeout(300);
  await p.evaluate(() => document.querySelector("[data-stage-thing=nights]")?.scrollIntoView({ block: "start" }));
  await p.evaluate(() => window.scrollBy(0, -80));
  await shot(p, { path: `${OUT}/hotels-${size}.png` });
  console.log(size, "days add", JSON.stringify(await runMove(p, "trip.add", 0)));
  await shot(p, { path: `${OUT}/days-${size}.png` });
  console.log(size, "checkout", JSON.stringify(await runMove(p, "trip.go", 2)));
  await p.waitForTimeout(500);
  await shot(p, { path: `${OUT}/checkout-${size}.png` });
  await p.context().close();
}
await browser.close();
