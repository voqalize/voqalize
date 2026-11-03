// Loads a built extension unpacked in Chromium on the live site and checks
// what can be checked without a real call (no key, no microphone):
//
//   - the widget renders, bottom corner, with the character's still;
//   - embed.config is requested from the page's own world, with the site's
//     Origin and the key as a Bearer token, credentials omitted;
//   - no Content-Security-Policy violation and no console error from the
//     extension's scripts;
//   - the console handle has the Site Agent's two Stage moves;
//   - in a call, the early shell puts the widget back on the next page of a
//     full page load before the site's own scripts run (the call is stood in
//     for by the state a page leaves behind when it unloads mid-call).
//
//   node build.mjs --site wom --out dist/wom-verify   (any key; a fake one is fine)
//   node test/verify-live.mjs dist/wom-verify https://www.wom.cl/ /planes/
//
// CHROMIUM names the browser (a Chrome for Testing or Chromium build; branded
// Chrome no longer loads unpacked extensions from the command line).

import { chromium } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const [extDir = "dist/wom", home = "https://www.wom.cl/", next = "/planes/"] = process.argv.slice(2);
const ext = resolve(extDir);
const exe = process.env.CHROMIUM;
const shots = resolve(process.env.SHOTS ?? "test-results");

const ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), "vq-ext-")), {
  executablePath: exe,
  headless: true,
  viewport: { width: 1440, height: 900 },
  locale: "es-CL",
  args: [`--disable-extensions-except=${ext}`, `--load-extension=${ext}`, "--headless=new"],
});

const problems = [];
const logs = [];
const embed = [];
ctx.on("console", (m) => logs.push(`[${m.type()}] ${m.text()}`));
ctx.on("weberror", (e) => problems.push(`page error: ${e.error().message}`));
ctx.on("request", async (r) => {
  if (r.url().includes("/embed.config")) {
    const h = await r.allHeaders();
    embed.push({ url: r.url(), method: r.method(), origin: h.origin, auth: (h.authorization ?? "").replace(/(pk_\w+?_).+/, "$1…"), cookie: Boolean(h.cookie) });
  }
});
ctx.on("response", (r) => {
  if (r.url().includes("/embed.config")) logs.push(`[net] embed.config → ${r.status()}`);
});
await ctx.addInitScript(() => {
  document.addEventListener("securitypolicyviolation", (e) =>
    console.error(`CSP violation: ${e.violatedDirective} blocked ${e.blockedURI}`),
  );
});

let [sw] = ctx.serviceWorkers();
sw ??= await ctx.waitForEvent("serviceworker", { timeout: 15000 });
console.log(`extension: ${sw.url()}`);

const page = await ctx.newPage();
page.on("console", (m) => {
  if (m.type() === "error") problems.push(`console error: ${m.text()} (${m.location().url})`);
});
await page.goto(home, { waitUntil: "domcontentloaded", timeout: 60000 });
await page.waitForSelector('[data-voqalize="widget"]', { state: "attached", timeout: 20000 });
await page.waitForTimeout(6000);
const widget = await page.evaluate(() => {
  const host = document.querySelector('[data-voqalize="widget"]');
  const shadow = host?.shadowRoot;
  // The still is the invite's picture: an <img>, or a background image.
  const img = shadow?.querySelector("img");
  const bg = [...(shadow?.querySelectorAll("*") ?? [])]
    .map((e) => getComputedStyle(e).backgroundImage)
    .find((b) => b && b.startsWith("url("));
  const boxes = [...(shadow?.children ?? [])].map((e) => e.getBoundingClientRect()).filter((r) => r.width && r.height);
  const r = boxes.sort((a, b) => b.width * b.height - a.width * a.height)[0];
  return {
    id: host?.id,
    text: (shadow?.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 120),
    still: img?.getAttribute("src") ?? bg?.slice(5, -2) ?? null,
    box: r ? { left: Math.round(r.left), top: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height) } : null,
    moves: window.__voqalizeWOM?.moves?.() ?? null,
  };
});
await page.screenshot({ path: join(shots, "verify-home.png") });

// The state a page leaves when it unloads mid-call, then a full page load.
await page.evaluate(() => {
  sessionStorage.setItem("voqalize.wom.call", JSON.stringify({
    status: "live", muted: false, activity: "listening", language: "es", still: null,
    home: { side: 20, bottom: 20 }, minimised: false, at: Date.now(),
  }));
});
await page.goto(new URL(next, home).href, { waitUntil: "commit", timeout: 60000 });
const early = await page.waitForFunction(
  () => {
    const host = document.querySelector('[data-voqalize="widget"]');
    if (!host) return null;
    return { shell: Boolean(window.__voqalize_wom_shell), readyState: document.readyState, parent: host.parentElement?.tagName };
  },
  null,
  { timeout: 20000, polling: 10 },
);
const shell = await early.jsonValue();
await page.waitForTimeout(1500);
await page.screenshot({ path: join(shots, "verify-next.png") });
const after = await page.evaluate(() => ({ url: location.href, widgets: document.querySelectorAll('[data-voqalize="widget"]').length }));

console.log(JSON.stringify({ widget, embed, shell, after }, null, 2));
console.log(logs.filter((l) => /voqalize|embed\.config|CSP/i.test(l)).join("\n"));
// A made-up key is refused (401) by embed.config: expected, and the only
// network error of ours a build without the real key can show.
const expected = (p) => /embed\.config/.test(p) && /status of 401/.test(p);
const ours = problems.filter((p) => /voqalize|chrome-extension|CSP/i.test(p) && !expected(p));
const refused = problems.filter(expected).length;
if (refused) console.log(`embed.config refused the key ${refused} time(s) (401): expected with a made-up key`);
console.log(ours.length ? `PROBLEMS (ours):\n${ours.join("\n")}` : "no CSP violation, no console error from the extension");
const theirs = problems.filter((p) => !ours.includes(p) && !expected(p));
if (theirs.length) console.log(`the site's own errors (${theirs.length}):\n${theirs.slice(0, 8).join("\n")}`);
await ctx.close();
