/**
 * His voice's loudness as a mouth shape (`src/level.ts`): the thresholds, what
 * the holder sends, and what the page's still shows. No browser.
 */

import { expect, test } from "@playwright/test";

import { CLOSE_MS, HOLD_MS, LevelSender, Mouth, REPEAT_MS, rmsOf, shapeOf, STALE_MS, windowSize } from "../src/level";

test.describe("loudness to a mouth shape", () => {
  test("the avatar's thresholds: closed to 0.01, small under 0.04, medium under 0.1, open above", () => {
    expect([0, 0.005, 0.01].map(shapeOf)).toEqual([0, 0, 0]);
    expect([0.0101, 0.039].map(shapeOf)).toEqual([1, 1]);
    expect([0.04, 0.099].map(shapeOf)).toEqual([2, 2]);
    expect([0.1, 0.7].map(shapeOf)).toEqual([3, 3]);
    expect(shapeOf(Number.NaN)).toBe(0);
  });

  test("the RMS of a window, and a window of about 20 ms", () => {
    expect(rmsOf([])).toBe(0);
    expect(rmsOf([0.5, -0.5, 0.5, -0.5])).toBeCloseTo(0.5);
    expect(windowSize(48_000)).toBe(1024);
    expect(windowSize(44_100)).toBe(1024);
    expect(windowSize(16_000)).toBe(256);
  });
});

test.describe("what the holder sends", () => {
  test("a shape when it changes, an open one again every REPEAT_MS, a closed one once", () => {
    const s = new LevelSender();
    expect(s.next(0, 0)).toBeNull();
    expect(s.next(2, 10)).toBe(2);
    expect(s.next(2, 30)).toBeNull();
    expect(s.next(2, 10 + REPEAT_MS)).toBe(2);
    expect(s.next(3, 10 + REPEAT_MS + 1)).toBe(3);
    expect(s.next(0, 400)).toBe(0);
    expect(s.next(0, 400 + REPEAT_MS * 3)).toBeNull();
  });
});

test.describe("what the page's still shows", () => {
  test("a new shape shows at once, and each is held at least HOLD_MS", () => {
    const m = new Mouth();
    m.hear(2, 0);
    expect(m.at(0)).toBe(2);
    m.hear(3, 10);
    expect(m.at(10)).toBe(2);
    expect(m.at(HOLD_MS - 1)).toBe(2);
    expect(m.at(HOLD_MS)).toBe(3);
  });

  test("the level at 0 closes the mouth CLOSE_MS later, not before", () => {
    const m = new Mouth();
    m.hear(3, 0);
    expect(m.at(0)).toBe(3);
    m.hear(0, 100);
    expect(m.at(100)).toBe(3);
    expect(m.at(100 + CLOSE_MS - 1)).toBe(3);
    expect(m.at(100 + CLOSE_MS)).toBe(0);
  });

  test("a gap shorter than CLOSE_MS between syllables does not shut it", () => {
    const m = new Mouth();
    m.hear(2, 0);
    m.at(0);
    m.hear(0, 100);
    expect(m.at(150)).toBe(2);
    m.hear(1, 200);
    expect(m.at(200)).toBe(1);
    m.hear(0, 260);
    expect(m.at(260 + CLOSE_MS - 1)).toBe(1);
  });

  test("no level for STALE_MS closes it, and then there is nothing left to show", () => {
    const m = new Mouth();
    m.hear(3, 0);
    expect(m.at(0)).toBe(3);
    expect(m.at(STALE_MS)).toBe(3);
    expect(m.busy(STALE_MS)).toBe(true);
    expect(m.at(STALE_MS + 1)).toBe(0);
    expect(m.busy(STALE_MS + 1)).toBe(false);
  });
});
