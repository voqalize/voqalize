// The adapter's host rule and the Calendly frame's time rule, in Node, with no
// browser: `pnpm test`. Node strips the types from `src/site.ts` itself.

import assert from "node:assert/strict";
import { test } from "node:test";

import { normTime, onThisTab, siteHost } from "../src/site.ts";

test("www and the bare host are one site", () => {
  assert.equal(siteHost("www.sendpotion.com"), "sendpotion.com");
  assert.equal(siteHost("SendPotion.com"), "sendpotion.com");
  assert.equal(siteHost("blog.sendpotion.com"), "blog.sendpotion.com");
});

test("a path on a www tab stays on www (prod, 2026-10-22)", () => {
  assert.equal(onThisTab("/pricing/", "https://www.sendpotion.com/?utm_source=x")?.href, "https://www.sendpotion.com/pricing/");
  assert.equal(onThisTab("/demo/", "https://www.sendpotion.com/es/")?.href, "https://www.sendpotion.com/demo/");
  assert.equal(onThisTab("/pricing/", "https://sendpotion.com/")?.href, "https://sendpotion.com/pricing/");
});

test("a full URL on the other host of the site is moved to this tab's host", () => {
  assert.equal(
    onThisTab("https://sendpotion.com/integrations/#top", "https://www.sendpotion.com/")?.href,
    "https://www.sendpotion.com/integrations/#top",
  );
});

test("another site is refused", () => {
  assert.equal(onThisTab("https://blog.sendpotion.com/x", "https://www.sendpotion.com/"), null);
  assert.equal(onThisTab("https://example.com/pricing/", "https://sendpotion.com/"), null);
  assert.equal(onThisTab("/pricing/", "https://blog.sendpotion.com/")?.href, "https://blog.sendpotion.com/pricing/");
});

test("a 24-hour slot and a 12-hour ask read the same (prod, 2026-10-22)", () => {
  // Calendly's data-start-time on a 24-hour calendar, and on a 12-hour one.
  assert.equal(normTime("12:00"), "12:00pm");
  assert.equal(normTime("14:30"), "2:30pm");
  assert.equal(normTime("09:00"), "9:00am");
  assert.equal(normTime("0:30"), "12:30am");
  assert.equal(normTime("3:00pm"), "3:00pm");
  // What Javier sends.
  assert.equal(normTime("12:00"), normTime("12:00pm"));
  assert.equal(normTime("3pm"), "3:00pm");
  assert.equal(normTime("3:00 PM"), "3:00pm");
  assert.equal(normTime("3:00 p.m."), "3:00pm");
  assert.equal(normTime("15:00"), normTime("3pm"));
});
