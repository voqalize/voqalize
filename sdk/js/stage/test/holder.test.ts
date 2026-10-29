/**
 * The holder routing jobs across page loads, driven through a stand-in for
 * `chrome.runtime` and the pages' ports: a new page finishes the move the
 * last one carried before it gets the jobs kept for it, and a job a load cut
 * off is never reported `applied`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { startHolder, type HolderCallbacks, type HolderClient } from "../src/extension/holder";
import type { FromPage, ToPage } from "../src/extension/protocol";
import { defineSite } from "../src/extension/site";
import type { StageProgress, StageResult } from "../src/wire.gen";

type Listener = (...a: any[]) => void;

interface FakePort {
  name: string;
  sender: { tab: { id: number }; url: string };
  posted: ToPage[];
  postMessage(m: ToPage): void;
  onMessage: { addListener(fn: Listener): void };
  onDisconnect: { addListener(fn: Listener): void };
  disconnect(): void;
  /** The page says something to the holder. */
  say(msg: FromPage): void;
  /** The page goes (a load). */
  leave(): void;
}

let connect: Listener;

function installChrome(): void {
  (globalThis as any).chrome = {
    runtime: {
      onConnect: { addListener: (fn: Listener) => (connect = fn) },
      onMessage: { addListener: () => {} },
      sendMessage: async () => ({ ok: true }),
    },
  };
}

function openPage(tab: number, url = "https://shop.test/"): FakePort {
  const onMsg: Listener[] = [];
  const onGone: Listener[] = [];
  const port: FakePort = {
    name: "voqalize",
    sender: { tab: { id: tab }, url },
    posted: [],
    postMessage(m) {
      port.posted.push(m);
    },
    onMessage: { addListener: (fn) => onMsg.push(fn) },
    onDisconnect: { addListener: (fn) => onGone.push(fn) },
    disconnect() {},
    say: (msg) => onMsg.forEach((fn) => fn(msg)),
    leave: () => onGone.forEach((fn) => fn()),
  };
  connect(port);
  return port;
}

const performs = (p: FakePort) =>
  p.posted.filter((m): m is Extract<ToPage, { k: "perform" }> => m.k === "perform");

function fakeCall() {
  const handlers = new Map<string, Set<Listener>>();
  const sent: { event: string; payload: any }[] = [];
  let callbacks: HolderCallbacks | null = null;
  const client: HolderClient = {
    on(name, fn) {
      (handlers.get(name) ?? handlers.set(name, new Set()).get(name)!).add(fn);
    },
    off(name, fn) {
      handlers.get(name)?.delete(fn);
    },
    sendUIEvent(event, payload) {
      sent.push({ event, payload });
    },
    connect: async () => undefined,
    disconnect: async () => {},
    disconnectBot() {},
    enableMic() {},
    sendClientMessage() {},
    transport: {},
  };
  return {
    client,
    sent,
    emit: (name: string, data?: unknown) => handlers.get(name)?.forEach((fn) => fn(data)),
    make: (_audio: HTMLAudioElement, cb: HolderCallbacks) => ((callbacks = cb), client),
    ready: () => callbacks!.onBotReady(),
  };
}

const site = defineSite({
  id: "shop",
  matches: ["https://shop.test/*"],
  home: "https://shop.test/",
  opening: "en",
  widget: { name: "Ana", languages: [{ code: "en", label: "EN" }], words: {} as never },
});

/** A call, live, with page `a` up and ready on tab 1. */
async function live() {
  const call = fakeCall();
  startHolder(site, { makeClient: call.make });
  const a = openPage(1);
  a.say({ k: "hello", url: "https://shop.test/", title: "Shop", front: true, ready: true });
  a.say({ ask: { op: "call", session: {}, language: "en" }, id: 1 } as never);
  await vi.advanceTimersByTimeAsync(0);
  call.ready();
  const move = (call_ref: string, move: string) =>
    call.emit("uiCommand", { command: "stage_move", payload: { call_ref, move, args: {}, when: "now" } });
  const results = () => call.sent.filter((s) => s.event === "stage_result").map((s) => s.payload as StageResult);
  const progress = () => call.sent.filter((s) => s.event === "stage_progress").map((s) => s.payload as StageProgress);
  return { call, a, move, results, progress };
}

beforeEach(() => {
  vi.useFakeTimers();
  installChrome();
});
afterEach(() => {
  vi.useRealTimers();
  delete (globalThis as any).chrome;
});

describe("a new page", () => {
  it("finishes the carried move before the jobs kept for it, in order", async () => {
    const { a, move, results, progress } = await live();
    move("m1", "core.page");
    await vi.advanceTimersByTimeAsync(0);
    const [p1] = performs(a);
    expect(p1!.job).toMatchObject({ kind: "stage", call_ref: "m1" });
    // The page carries the move to its next page and loads it.
    a.say({ k: "carried", call_ref: "m1", move: "core.page" });
    a.say({ k: "done", id: p1!.id, result: null, deferred: true });
    a.say({ k: "leaving" });
    a.leave();
    await vi.advanceTimersByTimeAsync(0);
    expect(results()).toMatchObject([{ call_ref: "m1", moved: true }]);

    // Two more moves while the tab loads: kept, saying so.
    move("m2", "cart.add");
    move("m3", "shop.filter");
    await vi.advanceTimersByTimeAsync(0);
    expect(progress().map((p) => [p.call_ref, p.phase])).toEqual([
      ["m2", "loading"],
      ["m3", "loading"],
    ]);

    // The next page says hello: not ready, so nothing is sent to it yet.
    const b = openPage(1, "https://shop.test/rooms");
    b.say({ k: "hello", url: "https://shop.test/rooms", title: "Rooms", front: true, ready: false });
    await vi.advanceTimersByTimeAsync(500);
    expect(performs(b)).toEqual([]);

    // It finishes the carried move (progress first: the carried wait starts again).
    await vi.advanceTimersByTimeAsync(15_000);
    b.say({ k: "progress", progress: { call_ref: "m1", move: "core.page", phase: "acting", ms: 15_600 } });
    await vi.advanceTimersByTimeAsync(10_000); // past the 20 s carried wait from the load
    b.say({ k: "result", result: { call_ref: "m1", move: "core.page", outcome: "applied", detail: "opened /rooms" } });
    expect(results().filter((r) => r.call_ref === "m1").map((r) => r.outcome)).toEqual(["applied", "applied"]);
    expect(results().some((r) => r.outcome === "failed")).toBe(false);
    expect(performs(b)).toEqual([]);

    // Ready: the kept jobs go, in the order they were asked for.
    b.say({ k: "ready" });
    expect(performs(b).map((p) => (p.job as { call_ref: string }).call_ref)).toEqual(["m2", "m3"]);
  });

  it("a page that never says ready gets its jobs after a while", async () => {
    const { a, move } = await live();
    a.say({ k: "leaving" });
    a.leave();
    move("m1", "shop.filter");
    await vi.advanceTimersByTimeAsync(0);
    const b = openPage(1);
    b.say({ k: "hello", url: "https://shop.test/", title: "Shop", front: true, ready: false });
    await vi.advanceTimersByTimeAsync(24_000);
    expect(performs(b)).toEqual([]);
    await vi.advanceTimersByTimeAsync(2_000);
    expect(performs(b)).toHaveLength(1);
  });

  it("a page from a build that never says whether it is ready gets its jobs at once", async () => {
    const { a, move } = await live();
    a.say({ k: "leaving" });
    a.leave();
    move("m1", "shop.filter");
    await vi.advanceTimersByTimeAsync(0);
    const b = openPage(1);
    b.say({ k: "hello", url: "https://shop.test/", title: "Shop", front: true });
    await vi.advanceTimersByTimeAsync(0);
    expect(performs(b)).toHaveLength(1);
  });
});

describe("a job a page load cut off", () => {
  it("never started: goes to the next page; started: unknown, never applied", async () => {
    const { a, move, results } = await live();
    move("m1", "shop.filter");
    await vi.advanceTimersByTimeAsync(0);
    expect(performs(a)).toHaveLength(1);
    // The page went before it began: the next page gets it.
    a.leave();
    const b = openPage(1);
    b.say({ k: "hello", url: "https://shop.test/", title: "Shop", front: true, ready: true });
    await vi.advanceTimersByTimeAsync(0);
    const [p] = performs(b);
    expect(p!.job).toMatchObject({ call_ref: "m1" });
    expect(results()).toEqual([]);
    // This one starts it, then goes: what it did is not known.
    b.say({ k: "progress", progress: { call_ref: "m1", move: "shop.filter", phase: "acting", ms: 10 } });
    b.leave();
    await vi.advanceTimersByTimeAsync(0);
    expect(results()).toMatchObject([{ call_ref: "m1", outcome: "unknown", detail: "the page left while it ran" }]);
  });

  it("a job cut off twice before it ran is unknown, never applied", async () => {
    const { a, move, results } = await live();
    move("m1", "shop.filter");
    await vi.advanceTimersByTimeAsync(0);
    a.leave();
    const b = openPage(1);
    b.say({ k: "hello", url: "https://shop.test/", title: "Shop", front: true, ready: true });
    await vi.advanceTimersByTimeAsync(0);
    b.leave();
    await vi.advanceTimersByTimeAsync(0);
    expect(results()).toMatchObject([{ call_ref: "m1", outcome: "unknown", detail: "the page left before it ran" }]);
  });

  it("a move that went on to another page owing nothing is unknown", async () => {
    const { a, move, results } = await live();
    move("m1", "core.page");
    await vi.advanceTimersByTimeAsync(0);
    const [p] = performs(a);
    a.say({ k: "done", id: p!.id, result: { call_ref: "m1", move: "core.page", outcome: "applied", moved: true } });
    await vi.advanceTimersByTimeAsync(0);
    expect(results()).toMatchObject([{ call_ref: "m1", outcome: "unknown" }]);
  });

  it("a result carries its timings and how it was set off", async () => {
    const { a, move, results } = await live();
    move("m1", "shop.filter");
    await vi.advanceTimersByTimeAsync(0);
    const [p] = performs(a);
    await vi.advanceTimersByTimeAsync(700);
    a.say({ k: "done", id: p!.id, result: { call_ref: "m1", move: "shop.filter", outcome: "applied", fired_ms: 50 } });
    await vi.advanceTimersByTimeAsync(0);
    expect(results()).toMatchObject([{ call_ref: "m1", fired: "now", queued_ms: 0, received_ms: 700, fired_ms: 50 }]);
  });
});
