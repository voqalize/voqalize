import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page, expect, test } from "@playwright/test";

const SHOTS = process.env.SHOTS_DIR ?? join(process.cwd(), "test-results", "shots");
mkdirSync(SHOTS, { recursive: true });

const DESKTOP = { width: 1280, height: 800 };
const PHONE = { width: 390, height: 780 };

/** Each state, the view and form it must reach, and the window it is drawn in. */
const STATES: { state: string; view: string; form: string; size?: { width: number; height: number } }[] = [
  { state: "closed-pill", view: "closed", form: "pill" },
  { state: "closed-face", view: "closed", form: "face" },
  { state: "closed-card", view: "closed", form: "card" },
  { state: "closed-none", view: "closed", form: "none" },
  { state: "closed-slotted", view: "closed", form: "pill" },
  { state: "open-card", view: "open", form: "card" },
  { state: "open-card-circle", view: "open", form: "card" },
  { state: "open-card-side", view: "open", form: "card" },
  { state: "open-large-top-left", view: "open", form: "card" },
  { state: "open-hero", view: "open", form: "hero" },
  { state: "inline", view: "open", form: "card" },
  { state: "collapsed-bubble", view: "collapsed", form: "bubble" },
  { state: "collapsed-pill", view: "collapsed", form: "pill" },
  { state: "collapsed-muted", view: "collapsed", form: "bubble" },
  { state: "mic-asking", view: "open", form: "card" },
  { state: "mic-blocked", view: "open", form: "card" },
  { state: "mic-muted", view: "open", form: "card" },
  { state: "mic-hint-devices", view: "open", form: "card" },
  { state: "ended", view: "ended", form: "card" },
  { state: "voice-only", view: "open", form: "card" },
  { state: "face-background", view: "open", form: "card" },
  { state: "captions-under", view: "open", form: "card" },
  { state: "dark", view: "open", form: "card" },
  { state: "dark-closed", view: "closed", form: "card" },
  { state: "mobile-launcher", view: "closed", form: "face", size: PHONE },
  { state: "mobile-sheet", view: "open", form: "sheet", size: PHONE },
  { state: "mobile-collapsed", view: "collapsed", form: "bubble", size: PHONE },
];

async function load(page: Page, state: string): Promise<void> {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  await page.goto(`${process.env.VQL_PAGE_URL}?state=${state}`);
  await expect(page.locator(`body[data-ready="${state}"]`)).toBeAttached();
  // Let transitions settle (reduced motion makes them instant) and the face's still decode.
  await page.waitForTimeout(150);
  expect(errors, "page errors").toEqual([]);
}

for (const { state, view, form, size } of STATES) {
  test(state, async ({ page }) => {
    await page.setViewportSize(size ?? DESKTOP);
    await load(page, state);
    const widget = page.locator("vql-widget");
    await expect(widget).toHaveAttribute("view", view);
    await expect(widget).toHaveAttribute("form", form);
    const violations = await page.evaluate(() => (window as unknown as { __violations: string[] }).__violations);
    expect(violations, "CSP violations").toEqual([]);
    await page.screenshot({ path: join(SHOTS, `${state}.png`) });
  });
}

test("the face is the same element from open to collapsed and back", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await load(page, "open-card");
  await page.evaluate(() => {
    const w = document.querySelector("vql-widget") as HTMLElement & { shadowRoot: ShadowRoot };
    (window as unknown as { face: Element | null }).face = w.shadowRoot.querySelector("vql-face");
  });
  // Escape collapses from anywhere inside the widget.
  await page.locator("vql-widget").locator("vql-mic").locator("button").first().focus();
  await page.keyboard.press("Escape");
  await expect(page.locator("vql-widget")).toHaveAttribute("view", "collapsed");
  await page.locator("vql-widget").locator(".expand").click();
  await expect(page.locator("vql-widget")).toHaveAttribute("view", "open");
  const same = await page.evaluate(() => {
    const w = document.querySelector("vql-widget") as HTMLElement & { shadowRoot: ShadowRoot };
    return w.shadowRoot.querySelector("vql-face") === (window as unknown as { face: Element | null }).face;
  });
  expect(same).toBe(true);
});

test("the launcher opens the call from the keyboard, and focus moves into it", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await load(page, "closed-pill");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect(page.locator("vql-widget")).toHaveAttribute("view", "open");
  const focused = await page.evaluate(() => {
    let el: Element | null = document.activeElement;
    const path: string[] = [];
    while (el) {
      path.push(el.tagName.toLowerCase());
      el = el.shadowRoot?.activeElement ?? null;
    }
    return path.join(" > ");
  });
  expect(focused).toContain("vql-mic");
});

test("a dragged widget snaps to the nearest corner, and arrow keys on the grip move it", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await load(page, "open-card");
  const stage = page.locator("vql-widget").locator(".stage");
  const box = await stage.boundingBox();
  if (!box) throw new Error("no stage");
  await page.mouse.move(box.x + 40, box.y + 60);
  await page.mouse.down();
  await page.mouse.move(200, 200, { steps: 8 });
  await page.mouse.up();
  await expect.poll(async () => (await page.locator("vql-widget").locator(".dock").boundingBox())?.x ?? 999).toBeLessThan(100);
  await page.locator("vql-widget").locator(".grip").focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect.poll(async () => (await page.locator("vql-widget").locator(".dock").boundingBox())?.x ?? 0).toBeGreaterThan(600);
  await page.screenshot({ path: join(SHOTS, "moved-top-right.png") });
});
