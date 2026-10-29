/**
 * The page's mouth clock (`carriedForward`, `src/extension/mouth-clock.ts`): the holder's newest delivery
 * of his voice, carried forward to the face's read, and never further than
 * `HOLD_MS` past it. No browser.
 */

import { describe, expect, it as test } from "vitest";

import { carriedForward, HOLD_MS } from "../src/extension/mouth-clock";

const newest = { timestamp: 1_800_000_000_000, rtpTimestamp: 960_000 };

describe("the mouth clock a page reads", () => {
  test("before any delivery there is nothing to read", () => {
    expect(carriedForward(null, newest.timestamp)).toBeNull();
  });

  test("a read soon after the newest delivery is carried to the read, at 48 kHz", () => {
    expect(carriedForward(newest, newest.timestamp + 30)).toEqual({
      timestamp: newest.timestamp + 30,
      rtpTimestamp: newest.rtpTimestamp + 30 * 48,
    });
  });

  test("a read long after it stops at HOLD_MS, so a pause still reads as one", () => {
    const held = { timestamp: newest.timestamp + HOLD_MS, rtpTimestamp: newest.rtpTimestamp + HOLD_MS * 48 };
    expect(carriedForward(newest, newest.timestamp + HOLD_MS)).toEqual(held);
    expect(carriedForward(newest, newest.timestamp + 5_000)).toEqual(held);
  });

  test("a read stamped before the delivery (the two documents' clocks a hair apart) is the delivery", () => {
    expect(carriedForward(newest, newest.timestamp - 2)).toEqual(newest);
  });

  test("the RTP timestamp wraps at 2^32, as the stream's does", () => {
    const late = { timestamp: newest.timestamp, rtpTimestamp: 2 ** 32 - 480 };
    expect(carriedForward(late, late.timestamp + 20)?.rtpTimestamp).toBe(480);
  });
});
