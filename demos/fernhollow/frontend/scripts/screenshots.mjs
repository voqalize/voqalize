/**
 * Screenshots of every key page at desktop (1440) and phone (390) width,
 * against a running `pnpm preview` (default http://localhost:4317).
 *
 *   node scripts/screenshots.mjs [baseUrl] [only-name-substring]
 *
 * Writes screenshots/<name>-<width>.png (gitignored).
 */
import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "screenshots");
const origin = process.argv[2] ?? "http://localhost:4317";
const only = process.argv[3];
const base = `${origin}/demos/fernhollow`;

const settle = (page, ms = 700) => page.waitForTimeout(ms);
const fire = async (page, command) => {
  await page.click(`.debug-fire[data-command="${command}"]`);
  await settle(page, 1400);
};

const SHOTS = [
  { name: "home", path: "/", full: true },
  { name: "room", path: "/room/living" },
  { name: "category-filters", path: "/category/dining-tables?opt=Finish%3AOak&max=3000", full: false },
  { name: "product", path: "/product/weathered-oak-dining-table" },
  {
    name: "cart-drawer",
    path: "/product/weathered-oak-dining-table",
    run: async (page) => {
      await page.click(".add-btn");
      await settle(page, 800);
    },
  },
  {
    name: "checkout",
    path: "/product/oak-and-rattan-floor-lamp",
    run: async (page) => {
      await page.click(".add-btn");
      await settle(page, 400);
      await page.goto(`${base}/checkout`);
      await settle(page);
    },
  },
  { name: "journal", path: "/journal" },
  { name: "article", path: "/journal/layering-light" },
  {
    name: "debug-room-board",
    path: "/?debug=1",
    run: async (page) => {
      await fire(page, "update_brief");
      await fire(page, "show_room_set");
      await settle(page, 1400);
    },
  },
  {
    name: "debug-compare",
    path: "/?debug=1",
    run: async (page) => {
      await fire(page, "show_compare");
    },
  },
  {
    name: "debug-savings",
    path: "/?debug=1",
    run: async (page) => {
      await fire(page, "show_room_set");
      await fire(page, "show_savings");
      await fire(page, "swap_piece");
    },
  },
  {
    name: "debug-product-voice",
    path: "/product/weathered-oak-dining-table?debug=1",
    run: async (page) => {
      await fire(page, "select_variant");
      await fire(page, "confirm_add");
    },
  },
];

await mkdir(out, { recursive: true });
const browser = await chromium.launch();
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
    await page.goto(`${base}${shot.path}`, { waitUntil: "networkidle" });
    await settle(page);
    if (shot.run) await shot.run(page);
    if (shot.full) {
      // Walk the page so lazy images load before a full-page capture.
      const h = await page.evaluate(() => document.body.scrollHeight);
      for (let y = 0; y < h; y += 600) {
        await page.evaluate((top) => window.scrollTo(0, top), y);
        await page.waitForTimeout(120);
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await settle(page, 500);
    }
    const file = join(out, `${shot.name}-${width}.png`);
    await page.screenshot({ path: file, fullPage: shot.full ?? false });
    console.log(`${file}${errors.length ? `  ERRORS: ${errors.join(" | ")}` : ""}`);
    await page.close();
  }
  await ctx.close();
}
await browser.close();
