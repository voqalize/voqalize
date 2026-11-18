/**
 * Screenshots of every landing at desktop (1440x900) and phone (390x844), plus
 * mid-flow states driven through the `?debug=1` console's `window.__chhatri`.
 *
 *   node scripts/screenshots.mjs [baseUrl] [outDir] [only-name-substring]
 *
 * baseUrl defaults to http://localhost:5405 (a running `pnpm dev --port 5405`);
 * outDir to ./screenshots (gitignored). CHROME=/path/to/chrome uses that binary.
 */
import { existsSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const origin = process.argv[2] ?? "http://localhost:5405";
const out = resolve(process.argv[3] ?? join(here, "..", "screenshots"));
const only = process.argv[4];
const base = `${origin}/demos/insurance`;

const SIZES = [
  ["desktop", { width: 1440, height: 900 }],
  ["phone", { width: 390, height: 844 }],
];

const ready = (page) => page.waitForFunction(() => !!window.__chhatri, null, { timeout: 15000 });
const closeConsole = async (page) => {
  await page.evaluate(() => document.querySelector('[aria-label="Close move console"]')?.click());
  await page.addStyleTag({ content: ".debug-fab{display:none!important}" });
};

const SHOTS = [
  { name: "home", path: "/" },
  { name: "product-car", path: "/insurance/car" },
  { name: "quote-health", path: "/quote/health" },
  { name: "my-policies", path: "/my-policies" },
  { name: "policy-car", path: "/my-policies/car-2026" },
  { name: "claim", path: "/claim" },
  {
    name: "a-car-quote-zero-dep",
    path: "/quote/car?debug=1",
    run: async (page) => {
      await ready(page);
      await page.evaluate(() => window.__chhatri.preset("Car quote, full, zero dep on"));
      await closeConsole(page);
      await page.waitForTimeout(900);
    },
  },
  {
    name: "b-policy-clause-marked",
    path: "/my-policies/car-2026?debug=1",
    run: async (page) => {
      await ready(page);
      await page.evaluate(() => window.__chhatri.preset("Mark a clause on the car policy"));
      await closeConsole(page);
      await page.waitForTimeout(900);
    },
  },
  {
    name: "c-motor-claim-filled",
    path: "/claim?debug=1",
    run: async (page) => {
      await ready(page);
      await page.evaluate(() => window.__chhatri.preset("Motor claim, several sections"));
      await closeConsole(page);
      await page.waitForTimeout(900);
    },
  },
  {
    name: "d-health-claim-review",
    path: "/claim?debug=1",
    run: async (page) => {
      await ready(page);
      await page.evaluate(() => window.__chhatri.preset("Health claim to review"));
      await page.evaluate(() => document.querySelector('[data-stage-part="declaration"] input')?.click());
      await closeConsole(page);
      await page.waitForTimeout(900);
    },
  },
  {
    name: "e-call-tile",
    path: "/quote/car?debug=1",
    run: async (page) => {
      await ready(page);
      await page.click(".debug-chip");
      await closeConsole(page);
      await page.waitForTimeout(900);
    },
  },
];

await mkdir(out, { recursive: true });
const fallback = "/home/samkeet/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";
const executablePath = process.env.CHROME ?? undefined;
let browser;
try {
  browser = await chromium.launch(executablePath ? { executablePath } : {});
} catch {
  browser = await chromium.launch(existsSync(fallback) ? { executablePath: fallback } : {});
}
for (const [label, viewport] of SIZES) {
  for (const shot of SHOTS) {
    if (only && !shot.name.includes(only)) continue;
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1, reducedMotion: "reduce" });
    const page = await context.newPage();
    page.on("pageerror", (e) => console.error(`[${shot.name}] page error:`, e.message));
    await page.goto(`${base}${shot.path}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(700);
    if (shot.run) await shot.run(page);
    const file = join(out, `${shot.name}-${label}.png`);
    await page.screenshot({ path: file, fullPage: false });
    console.log("wrote", file);
    await context.close();
  }
}
await browser.close();
