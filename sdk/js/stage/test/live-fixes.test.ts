/**
 * What two live dev calls taught the page runtime: a performer can say
 * `partial`; every move reports where it is and when each step happened; a
 * slow scroll never holds the cues behind it; and a cue's result says how it
 * fired and how far behind its words the screen moved.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { RING_SCROLL_MS, scrollToEl } from "../src/dom";
import { Moves } from "../src/moves";
import { Spotlight } from "../src/spotlight";
import { type FireInfo, Timeline, withFire } from "../src/timeline";
import type { StageCue, StageProgress } from "../src/wire.gen";

function box(el: Element, left: number, top: number, width: number, height: number): void {
  el.getBoundingClientRect = () =>
    ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON() {} }) as DOMRect;
}

afterEach(() => {
  document.documentElement.querySelectorAll("[data-voqalize]").forEach((n) => n.remove());
  document.body.innerHTML = "";
  vi.useRealTimers();
});

describe("a performer's result", () => {
  it("may be partial, with what it could not use", async () => {
    const moves = new Moves(new Spotlight({ color: "#000" }));
    moves.register("shop.filter", "reversible", async () => ({
      outcome: "partial" as const,
      detail: "King applied; Queen is not offered",
      refused: [{ arg: "size", why: "not offered", options: ["King", "Twin"] }],
    }));
    moves.register("shop.sort", "reversible", async () => ({ detail: "sorted by price" }));
    moves.register("shop.both", "reversible", async () => ({ refused: [{ arg: "colour", why: "sold out" }] }));
    expect(await moves.run("shop.filter", ["size", "King|Queen"], "p1")).toMatchObject({
      outcome: "partial",
      detail: "King applied; Queen is not offered",
      refused: [{ arg: "size", options: ["King", "Twin"] }],
      moved: false,
    });
    expect(await moves.run("shop.sort", {}, "p2")).toMatchObject({ outcome: "applied", detail: "sorted by price", refused: [] });
    // Something refused and nothing said: partial.
    expect(await moves.run("shop.both", {}, "p3")).toMatchObject({ outcome: "partial", detail: null });
  });
});

describe("progress and timings", () => {
  it("says queued, acting and ringing as they happen, and times each step from receipt", async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `<h2 id="t">Rooms</h2>`;
    box(document.getElementById("t")!, 0, 0, 100, 20);
    const said: StageProgress[] = [];
    const moves = new Moves(new Spotlight({ color: "#000", beatMs: 100 }), { onProgress: (p) => said.push(p) });
    const heard: StageProgress[] = [];
    const off = moves.listen((p) => heard.push(p));
    moves.register("core.wait", "look", async () => {
      await new Promise((r) => setTimeout(r, 500));
      return "waited";
    });
    moves.register("core.show", "look", async (_args, c) => {
      c.progress("waiting_site");
      await new Promise((r) => setTimeout(r, 200));
      await c.ring(document.getElementById("t")!);
      c.progress("confirming");
      return "shown";
    });
    const received = Date.now() - 1000; // the page had it a second before
    const first = moves.run("core.wait", {}, "a");
    const second = moves.run("core.show", {}, "b", { receivedAt: received });
    await vi.advanceTimersByTimeAsync(1000);
    const a = await first;
    const b = await second;
    expect(said.filter((p) => p.call_ref === "b").map((p) => p.phase)).toEqual([
      "queued",
      "acting",
      "waiting_site",
      "ringing",
      "acting",
      "confirming",
    ]);
    expect(said.find((p) => p.call_ref === "b" && p.phase === "queued")!.ms).toBe(1000);
    expect(heard).toEqual(said);
    off();
    expect(a).toMatchObject({ outcome: "applied", queued_ms: 0, fired_ms: 0, received_ms: 500 });
    expect(a!.ringed_ms).toBeUndefined();
    // b: received 1 s before it was queued; started when a ended (500 ms
    // later), rang after the site's 200 ms, ended after the 100 ms beat.
    expect(b).toMatchObject({ outcome: "applied", queued_ms: 1000, fired_ms: 1500, ringed_ms: 1700, received_ms: 1800 });
  });

  it("a carried move's timings run from when the first page received it", async () => {
    const moves = new Moves(new Spotlight({ color: "#000" }));
    const r = await moves.resume({ kind: "carried", call_ref: "c1", move: "core.page", received_at: Date.now() - 3000 });
    expect(r!.received_ms).toBeGreaterThanOrEqual(3000);
  });
});

describe("a slow scroll never holds the cues behind it", () => {
  /** A smooth scroll that crawls: 20 px every 80 ms. */
  function crawl(): () => void {
    let y = 0;
    let target = 0;
    Object.defineProperty(window, "scrollY", { configurable: true, get: () => y });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });
    Object.defineProperty(document.documentElement, "scrollHeight", { configurable: true, value: 100_000 });
    window.scrollBy = ((o: ScrollToOptions) => {
      target = y + (o.top ?? 0);
    }) as typeof window.scrollBy;
    const timer = setInterval(() => {
      if (y < target) y = Math.min(target, y + 20);
    }, 80);
    return () => clearInterval(timer);
  }

  it("waits for a scroll at most maxMs", async () => {
    vi.useFakeTimers();
    const stop = crawl();
    document.body.innerHTML = `<section id="far">Far</section>`;
    box(document.getElementById("far")!, 0, 20_000, 100, 50);
    let done = false;
    void scrollToEl(document.getElementById("far")!, { maxMs: RING_SCROLL_MS }).then(() => (done = true));
    await vi.advanceTimersByTimeAsync(RING_SCROLL_MS - 100);
    expect(done).toBe(false);
    await vi.advanceTimersByTimeAsync(200);
    expect(done).toBe(true);
    stop();
  });

  it("the next move due cuts the running move's scroll wait short", async () => {
    vi.useFakeTimers();
    const stop = crawl();
    document.body.innerHTML = `<section id="far">Far</section>`;
    box(document.getElementById("far")!, 0, 20_000, 100, 50);
    const moves = new Moves(new Spotlight({ color: "#000", beatMs: 0 }));
    const order: string[] = [];
    moves.register("core.show", "look", async (_a, c) => {
      await c.scrollTo(document.getElementById("far")!);
      order.push("scrolled");
      return "shown";
    });
    moves.register("core.next", "look", async () => {
      order.push("next");
      return "next";
    });
    const first = moves.run("core.show", {}, "a");
    await vi.advanceTimersByTimeAsync(170);
    const second = moves.run("core.next", {}, "b");
    await vi.advanceTimersByTimeAsync(100);
    expect(order).toEqual(["scrolled", "next"]);
    await Promise.all([first, second]);
    stop();
  });
});

describe("a cue's fire telemetry", () => {
  let n = 0;
  const cue = (at: string): StageCue => {
    n++;
    return { call_ref: `f${n}`, move: "core.show", verb: "show", args: [], at, before: 0, unit: 0 };
  };

  it("passes how and when each cue's words were heard, and says when one queues behind a move", async () => {
    vi.useFakeTimers();
    const infos: [string, FireInfo][] = [];
    const queued: string[] = [];
    let release: () => void = () => {};
    const tl = new Timeline(
      async (c, info) => {
        infos.push([c.call_ref, info]);
        if (infos.length === 1) await new Promise<void>((r) => (release = r));
      },
      { lang: "en", onQueued: (c) => queued.push(c.call_ref) },
    );
    const a = cue("the rooms are wide");
    const b = cue("and the spa is warm");
    tl.add(a);
    tl.add(b);
    tl.speaking();
    const t0 = Date.now();
    tl.hear("the rooms are wide");
    await vi.advanceTimersByTimeAsync(1000);
    tl.hear("and the spa is warm");
    await vi.advanceTimersByTimeAsync(10);
    expect(queued).toEqual([b.call_ref]);
    release();
    await vi.advanceTimersByTimeAsync(10);
    expect(infos.map(([ref, i]) => [ref, i.how, i.heardAt - t0])).toEqual([
      [a.call_ref, "anchor", 0],
      [b.call_ref, "anchor", 1000],
    ]);
    tl.clear();
  });

  it("withFire sets fired, queued_ms and lag_ms (start minus words heard)", () => {
    const info: FireInfo = { how: "fuzzy", heardAt: 10_000, firedAt: 10_200 };
    const r = withFire({ call_ref: "x", move: "m", outcome: "applied", fired_ms: 900 }, info, 9_500);
    expect(r).toMatchObject({ fired: "fuzzy", queued_ms: 700, lag_ms: 400 });
    // A result built without a start (a timeout, say) carries no lag.
    expect(withFire({ call_ref: "x", move: "m", outcome: "unknown" }, info, 9_500).lag_ms).toBeUndefined();
  });
});
