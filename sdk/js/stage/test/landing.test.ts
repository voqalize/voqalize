/**
 * A move reports as soon as its effect shows: trailing rings run after its
 * result, never before it; and a new page with no `ready()` waits only for its
 * DOM to settle, never for `load`.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { domSettled, SETTLE_MAX_MS, SETTLE_QUIET_MS } from "../src/dom";
import { Moves } from "../src/moves";
import { Spotlight } from "../src/spotlight";
import type { StageProgress, StageResult } from "../src/wire.gen";

function box(el: Element): void {
  el.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 100, height: 20, right: 100, bottom: 20, x: 0, y: 0, toJSON() {} }) as DOMRect;
}

afterEach(() => {
  document.documentElement.querySelectorAll("[data-voqalize]").forEach((n) => n.remove());
  document.body.innerHTML = "";
  vi.useRealTimers();
});

describe("a move's result as soon as its effect shows", () => {
  it("done() reports at once; the trailing ring runs after, and the next move waits for it", async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `<button id="opt">King</button><ol id="grid"><li>Liso Menta</li></ol>`;
    box(document.getElementById("opt")!);
    box(document.getElementById("grid")!);
    const order: string[] = [];
    const progress: StageProgress[] = [];
    const moves = new Moves(new Spotlight({ color: "#000", beatMs: 450 }), { onProgress: (p) => progress.push(p) });
    moves.register("shop.filter", "reversible", async (_a, c) => {
      // The act: its ring holds it a beat first.
      await c.ring(document.getElementById("opt")!);
      order.push("pressed");
      await new Promise((r) => setTimeout(r, 1000)); // the grid changes
      c.done("King applied; 16 products");
      order.push("reported");
      // What trails the effect: a ring on the grid.
      await c.ring(document.getElementById("grid")!);
      order.push("grid ringed");
      return "ignored: already reported";
    });
    moves.register("shop.next", "look", async () => {
      order.push("next");
      return "next";
    });
    let got: StageResult | null = null;
    const first = moves.run("shop.filter", {}, "a").then((r) => (got = r));
    const second = moves.run("shop.next", {}, "b");
    await vi.advanceTimersByTimeAsync(450 + 1000 + 10);
    expect(got).toMatchObject({ outcome: "applied", detail: "King applied; 16 products", call_ref: "a" });
    // Answered with the ring on the grid still holding its beat.
    expect(order).toEqual(["pressed", "reported"]);
    await vi.advanceTimersByTimeAsync(500);
    expect(order).toEqual(["pressed", "reported", "grid ringed", "next"]);
    await first;
    await second;
    // Past its result the move says no more of where it is.
    const after = progress.filter((p) => p.call_ref === "a").map((p) => p.phase);
    expect(after).toEqual(["acting", "ringing", "acting"]);
  });

  it("after() runs once the returned result is reported", async () => {
    vi.useFakeTimers();
    const order: string[] = [];
    const moves = new Moves(new Spotlight({ color: "#000" }));
    moves.register("shop.open", "navigate", async (_a, c) => {
      order.push("shown");
      c.after(async () => {
        await new Promise((r) => setTimeout(r, 1500));
        order.push("ringed");
      });
      return { detail: "Liso Menta is on screen" };
    });
    let got: StageResult | null = null;
    const run = moves.run("shop.open", {}, "p").then((r) => (got = r));
    await vi.advanceTimersByTimeAsync(1);
    expect(got).toMatchObject({ outcome: "applied", detail: "Liso Menta is on screen" });
    expect(order).toEqual(["shown"]);
    await vi.advanceTimersByTimeAsync(1500);
    expect(order).toEqual(["shown", "ringed"]);
    await run;
  });

  it("a failure after done() is only logged, and a partial can be reported early", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const moves = new Moves(new Spotlight({ color: "#000" }));
    moves.register("shop.filter", "reversible", async (_a, c) => {
      c.done({ outcome: "partial", detail: "King applied", refused: [{ arg: "color", why: "sold out" }] });
      throw new Error("the grid ring lost its target");
    });
    expect(await moves.run("shop.filter", {}, "x")).toMatchObject({ outcome: "partial", detail: "King applied" });
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe("a new page with no ready()", () => {
  it("waits for its DOM to be still, never for load", async () => {
    vi.useFakeTimers();
    let settled = false;
    void domSettled().then(() => (settled = true));
    await vi.advanceTimersByTimeAsync(SETTLE_QUIET_MS - 50);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(100);
    expect(settled).toBe(true);
  });

  it("a DOM that keeps changing is waited for until its cap, at most 1.5 s by default", async () => {
    // Real timers: the DOM's own observer delivers its records.
    const busy = setInterval(() => document.body.appendChild(document.createElement("i")), 20);
    const t0 = Date.now();
    await domSettled(100, 400);
    const took = Date.now() - t0;
    clearInterval(busy);
    expect(took).toBeGreaterThanOrEqual(380);
    expect(took).toBeLessThan(700);
    expect(SETTLE_MAX_MS).toBeLessThanOrEqual(1500);
  });
});
