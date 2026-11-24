/**
 * Screenshots of every landing page (desktop 1440x900, phone 390x844) and one
 * mid-flow state per agent, driven through the `?debug=1` console's scripts.
 *
 *   pnpm dev --port 5402 &
 *   node scripts/screenshots.mjs [baseUrl] [outDir]
 */
import { mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { chromium } from "playwright";

const BASE = process.argv[2] ?? "http://localhost:5402/demos/payroll_site";
const OUT = process.argv[3] ?? "screenshots";
const SHELL = "/home/samkeet/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";

const ROUTES = [
  ["home", "/"],
  ["modules", "/modules"],
  ["module-declarations", "/modules/declarations"],
  ["tax", "/tax"],
  ["customers", "/customers"],
  ["pricing", "/pricing"],
  ["book-demo", "/book-demo"],
];
const SIZES = {
  desktop: { width: 1440, height: 900 },
  phone: { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
};

await mkdir(OUT, { recursive: true });
let browser;
try {
  browser = await chromium.launch();
} catch {
  browser = await chromium.launch({ executablePath: existsSync(SHELL) ? SHELL : undefined });
}

for (const [size, viewport] of Object.entries(SIZES)) {
  const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height }, ...viewport });
  for (const [name, path] of ROUTES) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${OUT}/${name}-${size}.png` });
    if (name === "home" || name === "tax" || name === "pricing") {
      await page.screenshot({ path: `${OUT}/${name}-${size}-full.png`, fullPage: true });
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (overflow > 1) console.warn(`${name} ${size}: ${overflow}px horizontal overflow`);
  }
  await page.close();
}

/** One agent's main flow, run from the debug console, captured mid-flow and at its end. */
async function flow(label, path, button, size, fake) {
  const viewport = SIZES[size];
  const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height }, ...viewport });
  await page.goto(`${BASE}${path}?debug=1`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  if (fake) await page.getByRole("button", { name: fake, exact: true }).click();
  await page.getByRole("button", { name: button }).click();
  // The console is a dev tool: collapse it as soon as the script starts, so
  // neither frame shows it over the page (on a phone it covers the content).
  await page.locator(".debug-head").click();
  await page.waitForTimeout(2600);
  await page.screenshot({ path: `${OUT}/flow-${label}-${size}-mid.png` });
  // Open it again only to see when the script has finished, then collapse it.
  await page.locator(".debug-head").click();
  await page.waitForFunction(() => !document.querySelector("[data-debug-console] .debug-scripts button:disabled"), null, { timeout: 30000 });
  await page.locator(".debug-head").click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}/flow-${label}-${size}-end.png` });
  await page.close();
}

await flow("sdr", "/", "Sales rep on /", "desktop", "speaking");
await flow("pricing", "/pricing", "Pricing on /pricing", "desktop", "speaking");
await flow("booker", "/book-demo", "Booker on /book-demo", "desktop", "listening");
await flow("sdr", "/", "Sales rep on /", "phone");
await flow("booker", "/book-demo", "Booker on /book-demo", "phone");
await browser.close();
console.log(`screenshots in ${OUT}`);
