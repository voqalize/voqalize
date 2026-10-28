/**
 * The scheduler's frame script (`src/meetings.ts`, built as `meetings.js`) and
 * the adapter's `book_demo`, in the test build of the extension, against the
 * HubSpot Meetings frame as the probe saved it on 2026-10-28
 * (`../fixtures/meetings/`: the calendar, the times and the details step of
 * the stepped layout, en-US, Asia/Kolkata; scripts stripped). Headless, no
 * network.
 *
 * The saved steps are still pictures, so a small stand-in plays HubSpot's
 * React in the frame: a click on an open day shows the times step, a click on
 * a time the details step, Back the step before, and a press of Confirm that
 * reaches HubSpot is counted (`__confirmed`). Checked:
 *
 *   - the script acts only in a frame whose page is enveedo.com;
 *   - it reports the calendar (month, open days as ISO), then the times
 *     ("6:30pm", whatever the clock), the meeting lengths and the timezone;
 *   - a `book` order chooses the day and the time and fills the details
 *     with the native setter, and never presses Confirm;
 *   - the visitor's own press of Confirm is stopped before HubSpot sees it
 *     and reported as scheduled, blocked.
 */

import { type BrowserContext, chromium, expect, type Frame, type Page, test as base } from "@playwright/test";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const EXT = join(here, ".build", "ext");
const FIXTURES = join(here, "..", "..", "fixtures", "meetings");
const ORIGIN = "https://enveedo.com";
const MEETINGS = "https://meetings.hubspot.com";

const body = (name: string) => {
  const html = readFileSync(join(FIXTURES, `${name}.html`), "utf8");
  return html.match(/<body[^>]*>([\s\S]*)<\/body>/i)?.[1] ?? html;
};

/** HubSpot's React, played by a stand-in over the saved steps. */
function frameHtml(): string {
  const views = { calendar: body("calendar"), times: body("times"), details: body("details") };
  const json = JSON.stringify(views).replace(/</g, "\\u003c");
  const script = `
    window.__confirmed = 0;
    const V = ${json};
    const stack = ["calendar"];
    function show(n) {
      document.body.innerHTML = V[n];
      stack.push(n);
    }
    document.addEventListener("click", (e) => {
      const t = e.target.closest && e.target.closest("[data-test-id]");
      if (!t) return;
      const id = t.getAttribute("data-test-id");
      if (id === "available-date" && t.getAttribute("aria-disabled") !== "true") show("times");
      else if (id === "time-picker-btn") show("details");
      else if (id === "back-btn") { stack.pop(); show(stack.pop() || "calendar"); }
      else if (id === "forward-btn") window.__confirmed++;
    });
    document.addEventListener("focusout", () => {
      const ids = ["confirm-firstName-field", "confirm-lastName-field", "booking-form-field-email-input"];
      const all = ids.every((id) => { const el = document.querySelector("[data-test-id=" + id + "]"); return el && el.value; });
      const btn = document.querySelector("[data-test-id=forward-btn]");
      if (btn) btn.setAttribute("aria-disabled", all ? "false" : "true");
    });`;
  return `<!doctype html><html lang="en-us"><head><title>Meetings</title></head><body>${views.calendar}<script>${script}</script></body></html>`;
}

const DEMO_PAGE = `<!doctype html><html lang="en"><head><title>Book a Demo</title></head><body>
  <header class="header"><nav class="nav"></nav></header>
  <main id="main-content"><div id="hs_cos_wrapper_module_1791381102074"><h2>Request a product demo</h2></div>
  <div class="meetings-iframe-container" data-src="${MEETINGS}/elis-martinez?embed=true">
    <iframe src="${MEETINGS}/elis-martinez?embed=true&parentPageUrl=${encodeURIComponent(`${ORIGIN}/book-a-demo`)}" style="width:640px;height:760px;border:0"></iframe>
  </div></main>
  <script>window.__msgs = []; addEventListener("message", (e) => { if (e.origin === "${MEETINGS}") window.__msgs.push(e.data); });</script>
  <footer id="footer"></footer></body></html>`;

const test = base.extend<{ ctx: BrowserContext }>({
  // eslint-disable-next-line no-empty-pattern
  ctx: async ({}, use) => {
    const dir = mkdtempSync(join(tmpdir(), "enveedo-meetings-"));
    const ctx = await chromium.launchPersistentContext(dir, {
      channel: "chromium",
      headless: true,
      viewport: { width: 1280, height: 900 },
      locale: "en-US",
      timezoneId: "Asia/Kolkata",
      args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
    });
    await ctx.route(/^https?:/, async (route, request) => {
      const url = new URL(request.url());
      if (request.resourceType() !== "document") return route.fulfill({ status: 404, body: "" });
      if (url.origin === ORIGIN && url.pathname === "/book-a-demo") {
        return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: DEMO_PAGE });
      }
      if (url.origin === MEETINGS) return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: frameHtml() });
      return route.abort();
    });
    await use(ctx);
    await ctx.close();
  },
});

type Msg = Record<string, Record<string, unknown>>;
const msgs = (page: Page) => page.evaluate(() => (window as unknown as { __msgs: Msg[] }).__msgs);
/** The frame's newest state: reported by itself, or with its answer to an order. */
const lastState = async (page: Page) => {
  const m = [...(await msgs(page))].reverse().find((x) => x.voqalizeMeetings || x.voqalizeMeetingsDone);
  return m?.voqalizeMeetings ?? (m?.voqalizeMeetingsDone?.state as Record<string, unknown> | undefined);
};

async function demoPage(ctx: BrowserContext): Promise<{ page: Page; frame: Frame }> {
  const page = ctx.pages()[0] ?? (await ctx.newPage());
  await page.goto(`${ORIGIN}/book-a-demo`);
  const frame = await expect
    .poll(() => page.frames().find((f) => f.url().startsWith(MEETINGS)) ?? null)
    .not.toBeNull()
    .then(() => page.frames().find((f) => f.url().startsWith(MEETINGS))!);
  return { page, frame };
}

test.describe("the scheduler's frame", () => {
  test("reports the calendar, then the times, by test ids and timestamps", async ({ ctx }) => {
    const { page, frame } = await demoPage(ctx);
    await expect.poll(() => lastState(page)).toMatchObject({
      step: "calendar",
      month: "October 2026",
      days: ["2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31"],
      times: [],
    });
    // The visitor clicks a day: the stepped layout swaps in its times.
    await frame.locator("[data-test-id=available-date][aria-label='October 29th']").click();
    await expect.poll(() => lastState(page)).toMatchObject({
      step: "calendar",
      date: "2026-10-29",
      times: ["12:00am", "6:30pm", "6:45pm", "7:00pm", "8:45pm", "9:00pm", "10:45pm", "11:00pm"],
      duration: "15 mins",
      durations: ["15 mins", "30 mins", "1 hour"],
      timezone: expect.stringContaining("UTC +05:30"),
    });
  });

  test("a book order, through the adapter, picks the day and time and fills the details; Confirm is never pressed", async ({ ctx }) => {
    const { page, frame } = await demoPage(ctx);
    await page.waitForFunction(() => Boolean((window as unknown as { __voqalizeEnveedo?: unknown }).__voqalizeEnveedo));
    const failed = await page.evaluate(() =>
      (window as unknown as { __voqalizeEnveedo: { perform(c: string, p: unknown): Promise<unknown> } }).__voqalizeEnveedo.perform("book_demo", {
        duration: null, day: "2026-10-29", time: "6:30 PM", first_name: "Carolina", last_name: "Rojas", email: "carolina@acme.com",
      }),
    );
    expect(failed).toBeNull();
    expect(await frame.locator("[data-test-id=confirm-firstName-field]").inputValue()).toBe("Carolina");
    expect(await frame.locator("[data-test-id=confirm-lastName-field]").inputValue()).toBe("Rojas");
    expect(await frame.locator("[data-test-id=booking-form-field-email-input]").inputValue()).toBe("carolina@acme.com");
    await expect.poll(() => lastState(page)).toMatchObject({
      step: "details",
      date: "2026-10-29",
      time: "6:30pm",
      filled: { first_name: "Carolina", last_name: "Rojas", email: "carolina@acme.com" },
      missing: [],
    });
    await page.waitForTimeout(500);
    expect(await frame.evaluate(() => (window as unknown as { __confirmed: number }).__confirmed)).toBe(0);
    // The scheduler is rung on the page for the visitor.
    await expect(page.locator("[data-voqalize=highlight]")).toHaveCount(1);
  });

  test("a time it does not list is refused with the times it does", async ({ ctx }) => {
    const { page } = await demoPage(ctx);
    await page.waitForFunction(() => Boolean((window as unknown as { __voqalizeEnveedo?: unknown }).__voqalizeEnveedo));
    const failed = (await page.evaluate(() =>
      (window as unknown as { __voqalizeEnveedo: { perform(c: string, p: unknown): Promise<unknown> } }).__voqalizeEnveedo.perform("book_demo", {
        duration: null, day: "2026-10-29", time: "3:00pm", first_name: null, last_name: null, email: null,
      }),
    )) as { payload: { reason: string } } | null;
    expect(failed?.payload.reason).toContain("no 3:00pm");
    expect(failed?.payload.reason).toContain("6:30pm");
  });

  test("the visitor's own press of Confirm is stopped and reported, blocked", async ({ ctx }) => {
    const { page, frame } = await demoPage(ctx);
    await frame.locator("[data-test-id=available-date][aria-label='October 29th']").click();
    await frame.locator("[data-test-id=time-picker-btn]").nth(1).click();
    await frame.locator("[data-test-id=confirm-firstName-field]").fill("Carolina");
    await frame.locator("[data-test-id=forward-btn]").click({ force: true });
    await expect.poll(async () => (await msgs(page)).find((m) => m.voqalizeMeetingsScheduled)?.voqalizeMeetingsScheduled ?? null).toMatchObject({
      blocked: true,
      date: "2026-10-29",
      time: "6:30pm",
      filled: { first_name: "Carolina" },
    });
    expect(await frame.evaluate(() => (window as unknown as { __confirmed: number }).__confirmed)).toBe(0);
    await expect(frame.locator("[data-voqalize=toast]")).toContainText("not booked");
  });

  test("off enveedo.com (the scheduler's own page) the script does nothing", async ({ ctx }) => {
    const page = ctx.pages()[0] ?? (await ctx.newPage());
    await page.goto(`${MEETINGS}/elis-martinez`);
    await page.locator("[data-test-id=available-date][aria-label='October 29th']").click();
    await page.locator("[data-test-id=time-picker-btn]").first().click();
    await page.locator("[data-test-id=forward-btn]").click({ force: true });
    expect(await page.evaluate(() => (window as unknown as { __confirmed: number }).__confirmed)).toBe(1);
    await expect(page.locator("[data-voqalize=toast]")).toHaveCount(0);
  });
});
