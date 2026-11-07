import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type FrameLocator, type Locator, type Page, expect, test } from "@playwright/test";

const SHOTS = process.env.SHOTS_DIR ?? join(process.cwd(), "test-results", "shots");
mkdirSync(SHOTS, { recursive: true });

async function load(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("local.json")) errors.push(m.text());
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(process.env.VQL_BUILDER_URL ?? "");
  await expect(page.locator('body[data-ready="builder"]')).toBeAttached();
  return errors;
}

const desktop = (page: Page): FrameLocator => page.frameLocator("#frame-desktop");
const phone = (page: Page): FrameLocator => page.frameLocator("#frame-phone");

/** A field of the configuration the preview's widget is running, after its own defaults. */
function resolved(widget: Locator, path: string): Promise<unknown> {
  return widget.evaluate((w, p) => {
    let node: unknown = (w as unknown as { resolvedConfig: unknown }).resolvedConfig;
    for (const k of p.split(".")) node = (node as Record<string, unknown> | undefined)?.[k];
    return node;
  }, path);
}

test("the form drives the preview and the snippet", async ({ page }) => {
  const errors = await load(page);
  const snippet = page.locator("#snippet");
  const widget = desktop(page).locator("vql-widget");

  // Starts speaking, open in a card, with a snippet that changes nothing.
  await expect(widget).toHaveAttribute("view", "open");
  await expect(widget).toHaveAttribute("form", "card");
  await expect(phone(page).locator("vql-widget")).toHaveAttribute("form", "sheet");
  await expect(snippet).not.toContainText("config=");
  await page.screenshot({ path: join(SHOTS, "builder-default.png") });

  // The closed form: a face launcher.
  await page.locator('[data-state="closed"]').click();
  await expect(widget).toHaveAttribute("view", "closed");
  await page.locator('[data-path="launcher.style"] label:has-text("face")').click();
  await expect(widget).toHaveAttribute("form", "face");
  await expect(snippet).toContainText('"launcher":{"style":"face"}');

  // The brand colour, by its hex field.
  const hex = page.locator('[data-path="theme.brand"] .hex');
  await hex.fill("#0f766e");
  await hex.press("Enter");
  await expect(snippet).toContainText('"brand":"#0f766e"');
  await expect.poll(() => resolved(widget, "theme.brand")).toBe("#0f766e");

  // The anchor, from a select.
  await page.locator("#f-placement-anchor").selectOption("bottom-left");
  await expect(snippet).toContainText('"anchor":"bottom-left"');
  await expect.poll(() => resolved(widget, "placement.anchor")).toBe("bottom-left");

  // Captions off, then back to the default: the field leaves the snippet again.
  await page.locator('[data-path="captions.mode"] label:has-text("off")').click();
  await expect(snippet).toContainText('"captions":{"mode":"off"}');
  await page.locator('[data-path="captions.mode"] label:has-text("karaoke")').click();
  await expect(snippet).not.toContainText("captions");

  // A voice-only widget: the face's options go quiet.
  await page.locator("#f-avatar").uncheck();
  await expect(snippet).toContainText('"avatar":false');
  await expect(page.locator("#f-avatar-shape-circle")).toBeDisabled();

  // The React snippet reads the same configuration.
  await page.locator('[data-snippet="react"]').click();
  await expect(snippet).toContainText("VoqalizeWidget");
  await expect(snippet).toContainText('"avatar": false');

  // A link to the builder carries the configuration.
  const link = page.url();
  expect(link).toContain("#c=");
  const again = await page.context().newPage();
  await again.goto(link);
  await expect(again.locator("#snippet")).toContainText('"brand":"#0f766e"');
  await again.close();

  expect(errors).toEqual([]);
});

test("each state chip plays through the real widget", async ({ page }) => {
  const errors = await load(page);
  const widget = desktop(page).locator("vql-widget");
  const cases: [string, string, string][] = [
    ["collapsed", "collapsed", "bubble"],
    ["blocked", "open", "card"],
    ["ended", "ended", "card"],
    ["speaking", "open", "card"],
  ];
  for (const [state, view, form] of cases) {
    await page.locator(`[data-state="${state}"]`).click();
    await expect(widget).toHaveAttribute("view", view);
    await expect(widget).toHaveAttribute("form", form);
  }
  // The recorded turn lights the agent's words.
  await expect(widget.locator("vql-captions")).toContainText("This is how");
  // A dark sample page.
  await page.locator('[data-page="dark"]').click();
  await expect(desktop(page).locator("body.dark")).toBeAttached();
  await page.waitForTimeout(300);
  await page.screenshot({ path: join(SHOTS, "builder-dark.png") });
  expect(errors).toEqual([]);
});

test("the stubs say where the configuration goes", async ({ page }) => {
  await load(page);
  await expect(page.locator("#talk")).toBeDisabled();
  await page.locator("#apply").click();
  await expect(page.locator("#apply-dialog")).toContainText("widget settings");
  await expect(page.locator("#apply-json")).toHaveText("{}");
  await page.locator("#apply-dialog [data-close]").click();
  await page.locator("#from-site").click();
  await page.locator("#site-url").fill("https://example.com");
  await page.locator("#site-form button[type=submit]").click();
  await expect(page.locator("#site-result")).toContainText("Not connected yet");
});

test("the builder fits a phone", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(process.env.VQL_BUILDER_URL ?? "");
  await expect(page.locator('body[data-ready="builder"]')).toBeAttached();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({ path: join(SHOTS, "builder-phone.png"), fullPage: false });
  expect(errors).toEqual([]);
});
