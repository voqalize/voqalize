/**
 * The site's headers, and what the extension does about them (`rules.json`),
 * against the saved pages served over HTTPS with the headers the live site
 * sends (`site-headers.ts`, `server.ts`):
 *
 *   - on a page of the site (a strict Content-Security-Policy, and a
 *     Permissions-Policy that keeps the microphone to the page): the widget
 *     mounts, the call starts (the page's mint of the session reaches the
 *     API with the site's Origin), his face's runtime loads from the avatar's
 *     host, and the extension's grant frame may use the microphone;
 *   - on the booking (a loose policy without `blob:`, and no microphone for
 *     anyone): the same, with its CSP lifted too, since his face's textures
 *     load from `blob:` URLs and a policy that refuses them leaves him a
 *     white, untextured head (owner's dev call, 2026-10-27);
 *   - with the rules switched off (the negative control): the site's policy
 *     refuses the mint and the face's runtime, and keeps the microphone from
 *     the grant frame, which hands over to the grant tab.
 */

import { EXTENSION_ID, expect, makeHolder, ORIGIN, test, toHolder } from "./site-ext";
import type { Page } from "@playwright/test";

const EXT_ORIGIN = `chrome-extension://${EXTENSION_ID}`;
const widget = (page: Page) => page.locator("[data-voqalize=widget] .root");
const frameMayUseMic = (page: Page) =>
  page.evaluate((o) => (document as unknown as { featurePolicy: { allowsFeature(f: string, o: string): boolean } }).featurePolicy.allowsFeature("microphone", o), EXT_ORIGIN);
/** Whether the page's own world may reach `url` (its CSP's `connect-src`). */
const pageMayFetch = (page: Page, url: string) =>
  page.evaluate((u) => fetch(u, { method: "OPTIONS" }).then(() => true, () => false), url);
/** Whether the page may draw an image from a `blob:` URL, as his face's textures are. */
const pageMayShowBlob = (page: Page) =>
  page.evaluate(async () => {
    const png = Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([png], { type: "image/png" }));
    const img = new Image();
    return new Promise<boolean>((done) => { img.onload = () => done(true); img.onerror = () => done(false); img.src = url; });
  });

test.describe("the site's headers", () => {
  test("a page of the site: the widget, the call, his face's runtime and the grant frame all work under the rules", async ({ ext }) => {
    const page = await ext.open("/");
    expect(ext.site.documents).toContain("/");
    expect(await frameMayUseMic(page)).toBe(true);
    expect(await pageMayShowBlob(page)).toBe(true);
    // The page itself keeps the microphone too.
    expect(await page.evaluate(() => (document as unknown as { featurePolicy: { allowsFeature(f: string): boolean } }).featurePolicy.allowsFeature("microphone"))).toBe(true);

    await makeHolder(ext.sw);
    await toHolder(ext.sw, { what: "mic", answers: ["prompt", "granted"] });
    const framed = page.waitForEvent("framenavigated", (f) => f.url().includes("grant.html"));
    await page.locator("[data-voqalize=widget] .invite").click();
    expect((await framed).url()).toBe(`${EXT_ORIGIN}/grant.html?lang=es`);
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    expect(ext.site.connects).toHaveLength(1);
    expect(ext.site.connects[0].origin).toBe(ORIGIN);
    await expect(page.locator("[data-fake-avatar]")).toHaveAttribute("data-runtime", "loaded");
    // No grant tab was needed.
    expect(ext.ctx.pages().filter((p) => p.url().includes("grant.html"))).toHaveLength(0);
  });

  test("the booking: its policy is lifted so his face's blob: textures load, the microphone is allowed to the extension's frame alone, and the call starts", async ({ ext }) => {
    const page = await ext.open("/agenda-tu-hora/");
    expect(await frameMayUseMic(page)).toBe(true);
    // The booking's own policy still keeps the microphone from the page.
    expect(await page.evaluate(() => (document as unknown as { featurePolicy: { allowsFeature(f: string): boolean } }).featurePolicy.allowsFeature("microphone"))).toBe(false);
    // Its CSP refuses blob: images, his face's textures: it is lifted.
    expect(await pageMayShowBlob(page)).toBe(true);
    expect(await pageMayFetch(page, "https://api.voqalize.test/api/v1/ping")).toBe(true);
    await makeHolder(ext.sw);
    await toHolder(ext.sw, { what: "mic", answers: ["prompt", "granted"] });
    await page.locator("[data-voqalize=widget] .invite").click();
    await expect(widget(page)).toHaveAttribute("data-status", "live");
    expect(ext.site.connects[0].origin).toBe(ORIGIN);
    await expect(page.locator("[data-fake-avatar]")).toHaveAttribute("data-runtime", "loaded");
  });

  test("with the rules off, the site's own policy refuses the mint and the face, and the grant falls back to its tab", async ({ ext }) => {
    await ext.sw.evaluate(() => chrome.declarativeNetRequest.updateEnabledRulesets({ disableRulesetIds: ["headers"] }));
    const page = await ext.open("/");
    // The widget is the content script's, so it is there whatever the policy.
    await expect(widget(page)).toHaveAttribute("data-status", "idle");
    expect(await frameMayUseMic(page)).toBe(false);
    expect(await pageMayFetch(page, "https://api.voqalize.test/api/v1/ping")).toBe(false);
    expect(await pageMayShowBlob(page)).toBe(false);
    expect(await page.evaluate(() => import("https://avatar.voqalize.test/runtime.js" as string).then(() => true, () => false))).toBe(false);

    // The grant frame cannot ask here: it hands over to the grant tab.
    await makeHolder(ext.sw);
    await toHolder(ext.sw, { what: "mic", answers: ["prompt", "prompt", "granted"] });
    const tab = ext.ctx.waitForEvent("page", (p) => p.url().includes("grant.html"));
    await page.locator("[data-voqalize=widget] .invite").click();
    const grantTab = await tab;
    expect(grantTab.url()).toMatch(/grant\.html\?tab=1&lang=es$/);
    await grantTab.waitForEvent("close");
    // And the mint is refused by the page's connect-src: the call cannot start.
    await expect(widget(page)).toHaveAttribute("data-status", "error");
    expect(ext.site.connects).toHaveLength(0);
  });
});
