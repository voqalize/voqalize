/**
 * Screenshots of every screen, desktop (1440×900, the framed phone) and phone
 * (390×844, full screen), plus mid-flow states driven by the concierge's own
 * moves through the `?debug=1` console. Needs the dev server:
 * `pnpm dev --port 5470`, then `node scripts/screenshots.mjs [outDir]`.
 */
import { existsSync, mkdirSync } from "node:fs";
import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://localhost:5470/demos/belmonte";
const OUT = process.argv[2] ?? "screenshots";
const ONLY = process.env.ONLY ?? "";
mkdirSync(OUT, { recursive: true });
const CHROME = "/home/samkeet/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";
const browser = await chromium.launch(existsSync(CHROME) ? { executablePath: CHROME } : {});
const SIZES = { desktop: { width: 1440, height: 900 }, phone: { width: 390, height: 844 } };

async function open(size, path = "/", scenario = "arrival") {
  const ctx = await browser.newContext({ viewport: SIZES[size], deviceScaleFactor: size === "phone" ? 2 : 1 });
  const p = await ctx.newPage();
  p.on("pageerror", (e) => console.error("pageerror:", e.message));
  p.on("console", (m) => m.type() === "error" && console.error("console:", m.text()));
  await p.goto(`${BASE}/?debug=1`);
  await p.evaluate((s) => {
    localStorage.clear();
    sessionStorage.setItem("bm-debug", "1");
    localStorage.setItem("belmonte-guest-v1", JSON.stringify({ scenario: s }));
  }, scenario);
  await p.goto(`${BASE}${path}?debug=1`);
  await p.waitForTimeout(700);
  return p;
}
async function shot(p, name) {
  await p.evaluate(() => document.querySelector(".debug")?.setAttribute("style", "display:none"));
  await p.screenshot({ path: `${OUT}/${name}.png` });
  await p.evaluate(() => document.querySelector(".debug")?.removeAttribute("style"));
}
/** Fire the n-th sample of a move from the debug console; wait for its result. */
async function move(p, id, n = 0) {
  await p.evaluate(() => (window.__bmLast = undefined));
  const row = p.locator(".debug-row", { has: p.locator("b", { hasText: new RegExp(`^${id.replace(".", "\\.")}$`) }) });
  await row.locator("button").nth(n).click({ force: true });
  await p.waitForFunction(() => window.__bmLast !== undefined, null, { timeout: 30000 });
  const r = await p.evaluate(() => window.__bmLast);
  console.log(id, n, r?.outcome, r?.detail ?? "", r?.refused?.length ? JSON.stringify(r.refused) : "");
  return r;
}
const call = async (p, state) => {
  await p.locator(".debug-row", { has: p.locator("b", { hasText: /^Call$/ }) }).locator("button", { hasText: state }).click({ force: true });
  await p.waitForTimeout(500);
};
const tap = async (p, thing, sel) => {
  await p.evaluate(([t, q]) => document.querySelector(q || `[data-stage-thing="${t}"]`)?.click(), [thing, sel]);
  await p.waitForTimeout(400);
};

const PAGES = [
  ["home", "/"],
  ["dining", "/dining"],
  ["bar", "/bar"],
  ["spa", "/spa"],
  ["activities", "/activities"],
  ["meetings", "/meetings"],
  ["requests", "/requests"],
  ["visitors", "/visitors"],
  ["stay", "/stay"],
  ["checkin", "/stay/check-in"],
  ["checkout", "/stay/check-out"],
  ["info", "/info"],
];

for (const size of ["desktop", "phone"]) {
  if (!ONLY || ONLY === "pages") {
    const p = await open(size);
    for (const [name, path] of PAGES) {
      await p.goto(`${BASE}${path}?debug=1`);
      await p.waitForTimeout(500);
      await shot(p, `${name}-${size}`);
    }
    await p.context().close();
  }

  if (!ONLY || ONLY === "widget") {
    // The widget: a circle by default; a tap expands it; it folds back by itself.
    const p = await open(size, "/");
    await shot(p, `widget-idle-${size}`);
    await tap(p, "", ".bw-face");
    await shot(p, `widget-idle-open-${size}`);
    await call(p, "speaking");
    await p.waitForTimeout(5200);
    await shot(p, `widget-call-${size}`);
    await tap(p, "", ".bw-face");
    await shot(p, `widget-call-open-${size}`);
    await p.goto(`${BASE}/dining?debug=1`);
    await p.waitForTimeout(600);
    await tap(p, "item-belmonte-burger");
    await p.waitForTimeout(600);
    await shot(p, `widget-over-sheet-${size}`);
    await p.context().close();
  }

  if (!ONLY || ONLY === "checkin") {
    // Check-in, from Home, driven by her moves; the ID scan is the guest's own tap.
    const p = await open(size, "/");
    await move(p, "checkin.open", 0);
    await move(p, "checkin.confirm", 0);
    await tap(p, "id-scan");
    await p.waitForTimeout(2200);
    await call(p, "speaking");
    await move(p, "checkin.prefs", 0);
    await p.waitForTimeout(300);
    await shot(p, `flow-checkin-prefs-${size}`);
    await p.waitForTimeout(1200);
    await move(p, "checkin.early", 0);
    await p.waitForTimeout(1200);
    await shot(p, `flow-checkin-review-${size}`);
    await p.context().close();
  }

  if (!ONLY || ONLY === "dining") {
    const p = await open(size, "/", "departure");
    await call(p, "listening");
    await move(p, "menu.open", 0);
    await shot(p, `flow-dining-menu-${size}`);
    // A burger at 8:15 AM is refused (lunch from 11); breakfast scenario switch to arrival for lunch.
    await p.context().close();
    const q = await open(size, "/", "arrival");
    await q.evaluate(() => {
      const s = JSON.parse(localStorage.getItem("belmonte-guest-v1"));
      localStorage.setItem("belmonte-guest-v1", JSON.stringify({ ...s, checkedIn: true, room: "1412" }));
    });
    await q.goto(`${BASE}/dining?debug=1`);
    await q.waitForTimeout(600);
    await call(q, "speaking");
    const m = move(q, "menu.item", 0);
    await q.waitForTimeout(1500);
    await shot(q, `flow-dining-item-${size}`);
    await m;
    await move(q, "menu.item", 1);
    await move(q, "cart.open", 0);
    await q.waitForTimeout(600);
    await shot(q, `flow-dining-cart-${size}`);
    await q.context().close();
  }

  if (!ONLY || ONLY === "spa") {
    const p = await open(size, "/spa");
    await call(p, "speaking");
    await move(p, "spa.treatment", 1);
    await p.waitForTimeout(500);
    await shot(p, `flow-spa-times-${size}`);
    await p.context().close();
  }

  if (!ONLY || ONLY === "checkout") {
    const p = await open(size, "/", "departure");
    await call(p, "speaking");
    await move(p, "checkout.open", 0);
    await p.waitForTimeout(400);
    await shot(p, `flow-checkout-folio-${size}`);
    await move(p, "folio.dispute", 1);
    await p.waitForTimeout(300);
    await shot(p, `flow-checkout-dispute-${size}`);
    await move(p, "sheet.close", 0);
    await move(p, "late.pick", 1);
    await p.waitForTimeout(300);
    await shot(p, `flow-checkout-late-${size}`);
    await p.context().close();
  }

  if (!ONLY || ONLY === "more") {
    const p = await open(size, "/");
    await call(p, "listening");
    await move(p, "activity.show", 0);
    await p.waitForTimeout(300);
    await shot(p, `flow-activities-map-${size}`);
    await move(p, "visitor.open", 0);
    await p.waitForTimeout(300);
    await shot(p, `flow-visitor-${size}`);
    await move(p, "meeting.pick", 0);
    await p.waitForTimeout(1500);
    await shot(p, `flow-meeting-${size}`);
    await move(p, "request.fill", 1);
    await p.waitForTimeout(300);
    await shot(p, `flow-request-${size}`);
    await move(p, "info.open", 0);
    await p.waitForTimeout(300);
    await shot(p, `flow-info-pets-${size}`);
    await call(p, "idle");
    await shot(p, `idle-info-${size}`);
    await p.context().close();
  }
}
await browser.close();
