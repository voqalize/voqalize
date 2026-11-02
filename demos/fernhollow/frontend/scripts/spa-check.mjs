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
