/**
 * Screenshots of each page at desktop (1440×900) and phone (390×844), plus
 * mid-flow states driven through the `?debug=1` hook, against a running
 * `pnpm preview --port 5406` (or `pnpm dev --port 5406`).
 *
 *   node scripts/screenshots.mjs [origin] [outDir] [only-name-substring]
 *
 * Every shot starts from a fresh browser context (an empty demo session).
 * Moves run through `window.__dentalDebug.run(id, args)`, the same performers
 * a call uses, so the rings and effects are the real ones.
 */
import { existsSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const origin = process.argv[2] ?? "http://localhost:5406";
const out = process.argv[3] ?? join(here, "..", "screenshots");
const only = process.argv[4];
const base = `${origin}/demos/dental`;

const SIZES = [
  ["desktop", { width: 1440, height: 900 }],
  ["phone", { width: 390, height: 844 }],
];

const settle = (page, ms = 600) => page.waitForTimeout(ms);
async function hook(page) {
  await page.waitForFunction(() => !!window.__dentalDebug, null, { timeout: 10000 });
  const close = page.locator('.debug [aria-label="Close move console"]');
  if (await close.count()) await close.click();
}
async function run(page, id, args) {
  const res = await page.evaluate(
    async ([id, args]) => {
      const d = window.__dentalDebug;
      const a = args ?? d.examples()[id];
      const r = await d.run(id, a);
      return { outcome: r?.outcome, detail: r?.detail, refused: r?.refused };
    },
    [id, args ?? null],
  );
  console.log(`  ${id}: ${res.outcome} — ${res.detail}${res.refused?.length ? ` ${JSON.stringify(res.refused)}` : ""}`);
  return res;
}
/** Sign in the way a patient does: typing the number and the code (the agent never fills them). */
async function signIn(page, phone = "98450 31726") {
  await page.evaluate((phone) => {
    const { actions } = window.__dentalDebug;
    actions.openSignin();
    actions.setPhone(phone);
    actions.sendCode(phone);
    actions.setCode("4821");
    actions.verify("4821");
  }, phone);
  await settle(page, 300);
}

const SHOTS = [
  { name: "home", path: "/" },
  { name: "home-full", path: "/", full: true, sizes: ["desktop"] },
  {
    name: "menu-open",
    path: "/book",
    sizes: ["phone"],
    run: async (page) => {
      await page.click(".menu-btn");
      await settle(page, 300);
    },
    noHook: true,
  },
  { name: "book", path: "/book" },
  { name: "my-appointments", path: "/my-appointments" },
  {
    name: "book-hold",
    path: "/book?debug=1",
    run: async (page) => {
      await run(page, "book.slots");
      await settle(page, 1200);
      await run(page, "book.hold");
      await settle(page, 1800);
    },
  },
  {
    name: "book-rct-hold",
    path: "/book?debug=1",
    sizes: ["desktop"],
    run: async (page) => {
      const date = await page.evaluate(() => window.__dentalDebug.nextDay("rct", { dentist: "dr-kavitha" }));
      await run(page, "book.slots", { service_id: "rct", date, dentist_id: "dr-kavitha", view: "day" });
      await settle(page, 1000);
      await page.locator(".cal [data-slot] >> nth=2").click();
      await page.mouse.move(5, 300);
      await settle(page, 900);
    },
  },
  {
    name: "book-confirmed",
    path: "/book?debug=1",
    run: async (page) => {
      await run(page, "book.slots");
      await run(page, "book.hold");
      await signIn(page);
      await run(page, "book.confirm");
      await settle(page, 1600);
    },
  },
  {
    name: "book-week",
    path: "/book?debug=1",
    run: async (page) => {
      await signIn(page);
      await run(page, "cal.view", null);
      await settle(page, 1200);
    },
  },
  {
    name: "appts-signed-in",
    path: "/my-appointments?debug=1",
    run: async (page) => {
      await signIn(page);
      await settle(page, 800);
    },
  },
  {
    name: "appts-reschedule",
    path: "/my-appointments?debug=1",
    run: async (page) => {
      await signIn(page);
      await run(page, "appt.propose");
      await settle(page, 1600);
    },
  },
  {
    name: "appts-picker",
    path: "/my-appointments?debug=1",
    sizes: ["desktop"],
    run: async (page) => {
      await signIn(page);
      await page.click('[data-stage-thing="appt-DT-24063"] .appt-actions .btn >> nth=0');
      await settle(page, 600);
      await page.locator('[data-stage-thing="appt-DT-24063"] .picker').scrollIntoViewIfNeeded();
      await settle(page, 400);
    },
  },
  {
    name: "callback",
    path: "/my-appointments?debug=1",
    run: async (page) => {
      await signIn(page);
      await run(page, "callback.request");
      await settle(page, 1200);
    },
  },
  {
    name: "new-patient",
    path: "/book?debug=1",
    sizes: ["desktop"],
    run: async (page) => {
      await run(page, "book.slots");
      await run(page, "book.hold");
      await signIn(page, "+91 91234 56789");
      await settle(page, 600);
    },
  },
  {
    name: "call-connected",
    path: "/book?debug=1",
    run: async (page) => {
      await page.evaluate(() => window.__dentalDebug.fakeCall({ on: true, state: "speaking", heard: "Can I move my cleaning to next week?" }));
      await run(page, "site.show", { thing: "calendar" });
      await settle(page, 1200);
    },
  },
];

const HEADLESS = "/home/samkeet/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";
await mkdir(out, { recursive: true });
let browser;
try {
  browser = await chromium.launch();
} catch {
  browser = await chromium.launch({ executablePath: existsSync(HEADLESS) ? HEADLESS : undefined });
}
for (const shot of SHOTS) {
  if (only && !shot.name.includes(only)) continue;
  for (const [label, viewport] of SIZES) {
    if (shot.sizes && !shot.sizes.includes(label)) continue;
    const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, locale: "en-IN", timezoneId: "Asia/Kolkata" });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => console.log(`  [pageerror] ${e.message}`));
    console.log(`${shot.name}-${label}`);
    await page.goto(`${base}${shot.path}`, { waitUntil: "networkidle" });
    await settle(page, 900);
    if (shot.run) {
      if (!shot.noHook) await hook(page);
      await shot.run(page);
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (overflow > 0) console.log(`  [overflow] page is ${overflow}px wider than the viewport`);
    await page.screenshot({ path: join(out, `${shot.name}-${label}.png`), fullPage: !!shot.full });
    await ctx.close();
  }
}
await browser.close();
