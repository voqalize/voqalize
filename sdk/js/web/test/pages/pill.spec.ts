/**
 * The mic pill in a real browser, under the strict CSP: each state it can
 * show, light and dark, and the media manager's mic state and hint that
 * move it, through the package's own session. Also that a page with
 * captions, the device menu and the coach mark off never fetches their code.
 *
 * Screenshots go to `PILL_SHOTS_DIR` (default `<SHOTS_DIR>/pill`).
 */

import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Locator, type Page, expect, test } from "@playwright/test";

const SHOTS = process.env.PILL_SHOTS_DIR ?? join(process.env.SHOTS_DIR ?? join(process.cwd(), "test-results", "shots"), "pill");
mkdirSync(SHOTS, { recursive: true });

const DESKTOP = { width: 1280, height: 800 };
const PHONE = { width: 390, height: 780 };

/** The lazy chunks, by the file the page server gives each. */
const LAZY_FILES = ["devices.js", "coach.js", "captions-feature.js", "mic-pill.js"];

async function load(page: Page, state: string, scheme: "light" | "dark" = "light"): Promise<string[]> {
  const errors: string[] = [];
  const requested: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("request", (r) => requested.push(new URL(r.url()).pathname.slice(1)));
  await page.goto(`${process.env.VQL_PAGE_URL}?state=${state}${scheme === "dark" ? "&scheme=dark" : ""}`);
  await expect(page.locator(`body[data-ready="${state}"]`)).toBeAttached();
  await page.waitForTimeout(150);
  expect(errors, "page errors").toEqual([]);
  const violations = await page.evaluate(() => (window as unknown as { __violations: string[] }).__violations);
  expect(violations, "CSP violations").toEqual([]);
  return requested;
}

const widget = (page: Page) => page.locator("vql-widget");
const pill = (page: Page): Locator => widget(page).locator("vql-mic-pill");
/** The widget's polite region that reads the pill out. */
const announced = (page: Page) => widget(page).locator(".mic-said");

async function expectPill(page: Page, kind: string | null, text = ""): Promise<void> {
  if (kind === null) {
    await expect(pill(page)).toHaveCount(0);
    await expect(announced(page)).toHaveText("");
    return;
  }
  await expect(pill(page)).toHaveAttribute("kind", kind);
  await expect(pill(page).locator("[part=text]")).toHaveText(text);
  await expect(announced(page)).toHaveText(text);
}

const vql = (page: Page, action: string) =>
  page.evaluate((a) => (window as unknown as { __vql: Record<string, () => void> }).__vql[a](), action);

const sent = (page: Page) => page.evaluate(() => (window as unknown as { __vql: { sent(): unknown[] } }).__vql.sent());

const STATES: { state: string; kind: string; text: string; size?: { width: number; height: number } }[] = [
  { state: "pill-permission", kind: "permission", text: "Grant mic permission" },
  { state: "pill-asking", kind: "permission", text: "Grant mic permission" },
  { state: "pill-muted", kind: "muted", text: "You are muted" },
  { state: "pill-check-hint", kind: "check", text: "Is your mic working?" },
  { state: "pill-check-phone", kind: "check", text: "Is your mic working?", size: PHONE },
];

for (const { state, kind, text, size } of STATES) {
  for (const scheme of ["light", "dark"] as const) {
    test(`${state} (${scheme})`, async ({ page }) => {
      await page.setViewportSize(size ?? DESKTOP);
      await load(page, state, scheme);
      await expectPill(page, kind, text);
      await page.screenshot({ path: join(SHOTS, `${state}-${scheme}.png`) });
    });
  }
}

test("pressing the pill: permission shows the coach, muted unmutes, check opens the device menu", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await load(page, "pill-permission");
  await widget(page).locator("vql-coach").locator("[part=dismiss]").click();
  await expect(widget(page).locator("vql-coach")).toHaveCount(0);
  await pill(page).locator("[part=pill]").click();
  await expect(widget(page).locator("vql-coach")).toHaveAttribute("state", "blocked");

  await load(page, "pill-muted");
  await pill(page).locator("[part=pill]").click();
  await expectPill(page, null);
  await expect(widget(page).locator("vql-mic")).toHaveAttribute("state", "live");

  await load(page, "pill-check-hint");
  await pill(page).locator("[part=pill]").click();
  await expect(widget(page).locator("vql-devices")).toBeVisible();
  await page.screenshot({ path: join(SHOTS, "pill-check-devices-light.png") });
});

test("pressing the check pill on a phone shows this platform's advice", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await load(page, "pill-check-phone");
  await pill(page).locator("[part=pill]").click();
  await expect(widget(page).locator("vql-coach")).toHaveAttribute("state", "check");
  await page.screenshot({ path: join(SHOTS, "pill-check-phone-coach-light.png") });
});

for (const scheme of ["light", "dark"] as const) {
  test(`the media manager's mic state and hint move the pill (${scheme})`, async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await load(page, "pill-real", scheme);
    await expect(widget(page).locator("vql-mic")).toHaveAttribute("state", "live");
    await expectPill(page, null);

    // The device left, or the system silenced it.
    await vql(page, "lose");
    await expectPill(page, "check", "Is your mic working?");
    await expect(widget(page).locator("vql-coach")).toHaveAttribute("state", "missing");
    // The chip agrees with the pill rather than saying "Listening".
    await expect(widget(page).locator("vql-status")).toHaveAttribute("unheard", "");
    await expect(widget(page).locator("vql-status [part=word]")).toHaveText("Can't hear you");
    await page.screenshot({ path: join(SHOTS, `pill-device-gone-${scheme}.png`) });
    await vql(page, "restore");
    await expectPill(page, null);

    // Nothing about the mic goes to the agent.
    expect(await sent(page)).toEqual([]);
  });
}

test("a permission revoked mid-call asks for it, and a grant clears the pill", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await load(page, "pill-real");
  await expect(widget(page).locator("vql-mic")).toHaveAttribute("state", "live");
  await vql(page, "revoke");
  await expectPill(page, "permission", "Grant mic permission");
  await expect(widget(page).locator("vql-coach")).toHaveAttribute("state", "blocked");
  await page.screenshot({ path: join(SHOTS, "pill-permission-revoked-light.png") });
  await vql(page, "grant");
  await expect(widget(page).locator("vql-mic")).toHaveAttribute("state", "live");
  await expectPill(page, null);
});

test("with the pill off, the status chip carries the mic and nothing loads the pill", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  const requested = await load(page, "pill-off");
  await vql(page, "lose");
  await expect(widget(page).locator("vql-status")).toHaveAttribute("mic", "missing");
  await expect(widget(page).locator("vql-status")).not.toHaveAttribute("unheard", "");
  await expect(pill(page)).toHaveCount(0);
  expect(requested).not.toContain("mic-pill.js");
});

test("a page with captions, the device menu and the coach mark off never requests their chunks", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  const requested = await load(page, "lean");
  await expect(widget(page)).toHaveAttribute("view", "open");
  // Give any stray import time to start.
  await page.waitForTimeout(300);
  for (const file of LAZY_FILES) expect(requested, `${file} requested`).not.toContain(file);
  // The open-card page, with them on, does request captions: the check can fail.
  const full = await load(page, "open-card");
  await page.waitForTimeout(300);
  expect(full).toContain("captions-feature.js");
});
