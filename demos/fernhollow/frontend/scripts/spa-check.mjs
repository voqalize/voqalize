/**
 * The store is one page: no click and no brain `navigate` ever reloads it.
 *
 *   pnpm build && pnpm preview &      # serves /demos/fernhollow/ on :4317
 *   node scripts/spa-check.mjs [origin]
 *
 * Marks the window once (`__fhBoot`), clicks through the store, goes back and
 * forward, fires the brain's `navigate` for five pages, and asserts that the
 * mark survived, no second `load` happened, history grew by one entry per
 * move, Back restores the scroll position, and the voice dock's face mount
 * (`__fhVoice.face`, dev-only under ?debug=1) is the same instance throughout.
 * Exits non-zero on any failure.
 */
import { chromium } from "playwright";

const origin = process.argv[2] ?? "http://localhost:4317";
const base = `${origin}/demos/fernhollow`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
let loads = 0;
page.on("load", () => (loads += 1));

const fails = [];
const check = (ok, what) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${what}`);
  if (!ok) fails.push(what);
};
const path = () => (new URL(page.url()).pathname.replace("/demos/fernhollow", "") || "/") + new URL(page.url()).search;
const step = async (what, act, expect) => {
  await act();
  await page.waitForTimeout(450);
  const p = path();
  check(expect instanceof RegExp ? expect.test(p) : p === expect, `${what} → ${p}`);
};

await page.goto(`${base}/?debug=1`, { waitUntil: "networkidle" });
await page.waitForTimeout(600);
await page.evaluate(() => {
  window.__fhBoot = Date.now();
});
const boot = await page.evaluate(() => window.__fhBoot);
const face = await page.evaluate(() => window.__fhVoice?.face ?? null);
const history0 = await page.evaluate(() => history.length);
loads = 0;
await page.click('.debug [aria-label="Close action console"]');

let pushes = 0;
const push = async (what, act, expect) => {
  await step(what, act, expect);
  pushes += 1;
};

await push("header: Living", () => page.click('.main-nav a[href$="/room/living"]'), "/room/living");
await push("room: category pill", () => page.click(".pills a >> nth=0"), /^\/category\//);
await push("category: product card", () => page.click(".card-title a >> nth=0"), /^\/product\//);
await page.click(".add-btn");
await page.waitForTimeout(300);
await push("cart drawer: View cart", () => page.click(".drawer-foot >> text=View cart"), "/cart");
await push("header: Journal", () => page.click('.main-nav a[href$="/journal"]'), "/journal");
await page.evaluate(() => window.scrollTo(0, 900));
await page.waitForTimeout(300);
const journalY = await page.evaluate(() => window.scrollY);
await push("journal: article", () => page.click(".journal-grid-index .journal-card >> nth=0"), /^\/journal\/.+/);
await push("article: product card", () => page.click(".inline-product .link >> nth=0"), /^\/product\//);
await push("footer: Start a return", () => page.click('footer a[href$="/returns"]'), "/returns");
await page.click(".demo-order >> nth=0");
await push("returns: Find order", () => page.click("text=Find order"), /^\/returns\/start\?order=FH-/);

await step("back", () => page.goBack(), "/returns");
await step("back", () => page.goBack(), /^\/product\//);
await step("back", () => page.goBack(), /^\/journal\/.+/);
await step("back", () => page.goBack(), "/journal");
const restoredY = await page.evaluate(() => window.scrollY);
check(Math.abs(restoredY - journalY) < 40, `back restores the scroll position (${restoredY} vs ${journalY})`);
await step("forward", () => page.goForward(), /^\/journal\/.+/);
await step("forward", () => page.goForward(), /^\/product\//);
await step("forward", () => page.goForward(), "/returns");
await step("forward", () => page.goForward(), /^\/returns\/start/);

const NAV = [
  ["home", "/"],
  ["category/sofas", "/category/sofas"],
  ["product/weathered-oak-dining-table", "/product/weathered-oak-dining-table"],
  ["journal/layering-light", "/journal/layering-light"],
  ["returns/start?order=FH-20418", "/returns/start?order=FH-20418"],
];
for (const [pageName, want] of NAV) {
  await push(`brain navigate ${pageName}`, () => page.evaluate((p) => window.__fhDispatch("navigate", { page: p }), pageName), want);
}
await page.waitForTimeout(400);
check((await page.evaluate(() => window.scrollY)) < 40, "a push lands at the top of the new page");
check((await page.inputValue('input[name="order_number"]')) === "FH-20418", "returns form prefilled from navigate's query string");

// Circle to ask: real Shift-drags on the home page.
await push("brain navigate home (for the circle)", () => page.evaluate(() => window.__fhDispatch("navigate", { page: "home" })), "/");
const count = () => page.textContent(".selection-count").then(Number).catch(() => 0);
const badges = () => page.$$eval(".selection-badge", (x) => x.map((b) => b.textContent).sort());
/** Shift (+ Alt) drag a loop round a share of `sel`'s width. */
async function circle(sel, from, to, { alt = false, escapeMidway = false } = {}) {
  await page.evaluate((s) => document.querySelector(s)?.scrollIntoView({ block: "center" }), sel);
  await page.waitForTimeout(350);
  const r = await page.locator(sel).boundingBox();
  const cx = r.x + r.width * ((from + to) / 2);
  const cy = r.y + r.height / 2;
  const rx = (r.width * (to - from)) / 2 + 10;
  const ry = r.height * 0.75;
  await page.keyboard.down("Shift");
  if (alt) await page.keyboard.down("Alt");
  await page.mouse.move(cx + rx, cy);
  await page.mouse.down();
  for (let i = 1; i <= 48; i++) {
    await page.mouse.move(cx + Math.cos((i / 44) * 2 * Math.PI) * rx, cy + Math.sin((i / 44) * 2 * Math.PI) * ry, { steps: 2 });
    if (escapeMidway && i === 24) await page.keyboard.press("Escape");
  }
  await page.mouse.up();
  if (alt) await page.keyboard.up("Alt");
  await page.keyboard.up("Shift");
  await page.waitForTimeout(500);
}
await circle(".rooms-row", 0, 0.6);
check(path() === "/", `a Shift-drag that starts on a link does not follow it (${path()})`);
const first = await count();
check(first >= 3, `Shift + drag selects the circled room tiles (${first})`);
await circle(".rooms-row", 0.72, 1);
const second = await count();
check(second >= 1 && second < first, `a second circle replaces the first (${first} → ${second})`);
const before = second;
await circle(".rooms-row", 0, 0.3, { alt: true });
const after = await count();
const nums = await badges();
check(after > before && nums.join(",") === Array.from({ length: after }, (_, i) => String(i + 1)).sort().join(","), `Shift+Alt adds, badges continue (${before} → ${after}: ${nums.join(" ")})`);
await push("navigate after circling", () => page.evaluate(() => window.__fhDispatch("navigate", { page: "shop" })), "/shop");
check(!(await page.$(".selection-chip")) && (await badges()).length === 0, "navigation clears the selection (no chip, no badges)");
await push("back home", () => page.evaluate(() => window.__fhDispatch("navigate", { page: "home" })), "/");
await circle(".rooms-row", 0, 0.6);
await page.keyboard.press("Escape");
await page.waitForTimeout(200);
check(!(await page.$(".selection-chip")), "Esc clears the selection");
await circle(".rooms-row", 0, 0.6, { escapeMidway: true });
check(!(await page.$(".selection-chip")) && !(await page.$(".circle-ink")), "Esc while drawing drops the stroke and selects nothing");
await page.evaluate(() => window.__fhCircle());
await page.waitForTimeout(900);
check((await count()) === 3, "the fake circle selects three on-sale products");
const ordinary = await page.evaluate(() => document.getSelection()?.toString() ?? "");
check(ordinary === "", "no text got selected by the gestures");

check((await page.evaluate(() => window.__fhBoot)) === boot, "window mark __fhBoot unchanged (no reload)");
check(loads === 0, `no load event after the first (${loads})`);
check((await page.evaluate(() => window.__fhVoice?.face ?? null)) === face && face !== null, "the voice dock's face mount is the same instance");
const history1 = await page.evaluate(() => history.length);
check(history1 - history0 === pushes, `history grew by one entry per move (${history1 - history0} of ${pushes})`);
const cartCount = await page.textContent('[data-spot="button:cart"] .count-dot').catch(() => null);
check(cartCount === "1", `cart still holds the item added on the way (${cartCount})`);
check(errors.length === 0, `no page errors ${errors.join(" | ")}`);

await browser.close();
console.log(fails.length ? `\n${fails.length} failed` : "\nall passed");
process.exit(fails.length ? 1 : 0);
