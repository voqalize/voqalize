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
  {
    name: "circle-added",
    path: "/?debug=1",
    run: async (page) => {
      await page.click('.debug [aria-label="Close action console"]');
      await page.evaluate(async () => {
        const tiles = [...document.querySelectorAll(".rooms-row [data-fh-thing]")].filter((e) => e.getBoundingClientRect().right <= window.innerWidth);
        await window.__fhCircle({ els: tiles.slice(0, 2) });
        await new Promise((r) => setTimeout(r, 300));
        await window.__fhCircle({ els: tiles.slice(-1), additive: true });
      });
      await settle(page, 1000);
    },
  },
  {
    name: "circle-drawing",
    path: "/?debug=1",
    run: async (page) => {
      await page.click('.debug [aria-label="Close action console"]');
      await page.evaluate(() => window.__fhCircle({ upTo: 0.78, hold: true }));
      await settle(page, 120);
    },
  },
  {
    name: "circle-selected",
    path: "/?debug=1",
    run: async (page) => {
      await page.click('.debug [aria-label="Close action console"]');
      await page.evaluate(() => window.__fhCircle());
      await settle(page, 1100);
    },
  },
  {
    name: "choices",
    path: "/category/sofas?debug=1",
    run: async (page) => {
      await page.mouse.wheel(0, 380);
      await settle(page, 900);
      await fire(page, "show_choices");
    },
  },
  {
    name: "checkout-fill",
    path: "/product/weathered-oak-dining-table?debug=1",
    run: async (page) => {
      await page.click(".add-btn");
      await settle(page, 300);
      await page.keyboard.press("Escape");
      for (let i = 0; i < 5; i++) await fire(page, "checkout_fill");
      await settle(page, 300);
    },
  },
  {
    name: "call-connected",
    path: "/product/weathered-oak-dining-table?debug=1",
    run: async (page) => {
      await page.click('[data-fake="connect"]');
      await page.click('[data-fake="speak"]');
      await settle(page, 900);
    },
  },
  {
    name: "call-dragged",
    path: "/?debug=1",
    run: async (page) => {
      await page.click('[data-fake="connect"]');
      await page.click('.debug [aria-label="Close action console"]');
      await settle(page, 900);
      const box = await page.locator(".call-tile").boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + 40);
      await page.mouse.down();
      await page.mouse.move(80, 300, { steps: 8 });
      await page.mouse.up();
      await settle(page, 900);
    },
  },
  { name: "returns-home", path: "/returns" },
  {
    name: "returns-form",
    path: "/returns/start?order=FH-20418",
    run: async (page) => {
      await page.fill('input[name="email"]', "sam.rivera@example.com");
      await page.click(".rstep.is-open >> text=Continue");
      await settle(page, 300);
      await page.click('[data-stage-part="items:desk-chair-with-aluminum-frame"]');
      await page.click(".rstep.is-open >> text=Continue");
      await settle(page, 300);
      await page.click('[data-stage-part="reason:doesnt_suit_room"]');
      await settle(page, 400);
    },
  },
  {
    name: "returns-confirmation",
    path: "/returns/start?order=FH-20418",
    run: async (page) => {
      await page.fill('input[name="email"]', "sam.rivera@example.com");
      await page.click(".rstep.is-open >> text=Continue");
      await page.click('[data-stage-part="items:desk-chair-with-aluminum-frame"]');
      await page.click(".rstep.is-open >> text=Continue");
      await page.click('[data-stage-part="reason:doesnt_suit_room"]');
      await page.click('[data-stage-part="condition:unused_in_packaging"]');
      await page.click(".rstep.is-open >> text=Continue");
      await page.click('[data-stage-part="resolution:exchange"]');
      await page.click('[data-stage-part="exchange_variant_desk-chair-with-aluminum-frame:Walnut"]');
      await page.click(".rstep.is-open >> text=Continue");
      await page.click('[data-stage-part="collection:pickup"]');
      await page.click('[data-stage-part="pickup_window:saturday"]');
      await page.click(".rstep.is-open >> text=Continue");
      await settle(page, 300);
      await page.click('button:has-text("Submit return")');
      await settle(page, 700);
    },
  },
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
    // The console has done its job once the commands are fired; get it out of the picture.
    if (await page.$(".debug [aria-label=\"Close action console\"]")) await page.click('.debug [aria-label="Close action console"]');
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
