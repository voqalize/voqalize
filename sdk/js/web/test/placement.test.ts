import { describe, expect, it } from "vitest";
import {
  ANCHORS,
  BOTTOM_LIFT,
  PlacementController,
  type PlacementOptions,
  boxAt,
  clampPoint,
  clearPlace,
  fallbackOrder,
  marginsFrom,
  nearestAnchor,
  rememberKey,
  rememberPlace,
  rememberedPlace,
} from "../src/controllers/placement.js";

const view = { width: 1200, height: 800 };
const size = { width: 200, height: 100 };
const m = marginsFrom(16);

describe("geometry", () => {
  it("places each anchor inside the margins, bottom ones lifted", () => {
    expect(boxAt("bottom-right", size, view, m)).toEqual({ x: 984, y: 800 - 16 - BOTTOM_LIFT - 100 });
    expect(boxAt("top-left", size, view, m)).toEqual({ x: 16, y: 16 });
    expect(boxAt("bottom-center", size, view, m).x).toBe(500);
    expect(boxAt("middle-left", size, view, m).y).toBe(350);
  });

  it("keeps topClear free", () => {
    expect(boxAt("top-right", size, view, marginsFrom(16, 64)).y).toBe(80);
    expect(clampPoint({ x: 0, y: 0 }, size, view, marginsFrom({ x: 8, y: 10 }, 50))).toEqual({ x: 8, y: 60 });
  });

  it("clamps into a viewport smaller than the box without going negative", () => {
    const p = clampPoint({ x: 500, y: 500 }, size, { width: 100, height: 50 }, m);
    expect(p).toEqual({ x: 16, y: 16 });
  });

  it("snaps to the nearest anchor", () => {
    expect(nearestAnchor({ x: 30, y: 600 }, size, view, m)).toBe("bottom-left");
    expect(nearestAnchor({ x: 950, y: 20 }, size, view, m)).toBe("top-right");
    expect(nearestAnchor({ x: 520, y: 650 }, size, view, m)).toBe("bottom-center");
    expect(nearestAnchor({ x: 1000, y: 360 }, size, view, m)).toBe("middle-right");
  });

  it("falls back on the same side first, then the other", () => {
    expect(fallbackOrder("bottom-right")).toEqual([
      "bottom-right",
      "middle-right",
      "top-right",
      "bottom-left",
      "middle-left",
      "top-left",
      "bottom-center",
    ]);
    expect(new Set(fallbackOrder("bottom-center"))).toEqual(new Set(ANCHORS));
  });

  it("lifts above a bottom bar it would cover", () => {
    const bar = { left: 0, top: 740, width: 1200, height: 60 };
    const placed = clearPlace("bottom-right", size, view, m, [bar]);
    expect(placed.anchor).toBe("bottom-right");
    expect(placed.point.y).toBe(740 - 16 - 100);
  });

  it("moves to another anchor when lifting does not fit", () => {
    const column = { left: 900, top: 0, width: 300, height: 800 };
    const placed = clearPlace("bottom-right", size, view, m, [column]);
    expect(placed.anchor).toBe("bottom-left");
  });

  it("stays put when nothing is clear", () => {
    const all = { left: 0, top: 0, width: 1200, height: 800 };
    expect(clearPlace("top-left", size, view, m, [all]).anchor).toBe("top-left");
  });
});

class MemoryStorage {
  data = new Map<string, string>();
  getItem(k: string) {
    return this.data.get(k) ?? null;
  }
  setItem(k: string, v: string) {
    this.data.set(k, v);
  }
}

function scope(session = new MemoryStorage(), local = new MemoryStorage()) {
  return { sessionStorage: session, localStorage: local } as unknown as typeof globalThis;
}

describe("remember", () => {
  it("keeps a place per agent in the tab or the site", () => {
    const s = scope();
    rememberPlace("tab", "agent_a", { anchor: "top-left" }, s);
    expect(rememberedPlace("tab", "agent_a", s)).toEqual({ anchor: "top-left" });
    expect(rememberedPlace("tab", "agent_b", s)).toBeNull();
    expect(rememberedPlace("site", "agent_a", s)).toBeNull();
    rememberPlace("site", undefined, { free: { fx: 0.5, fy: 2 } }, s);
    expect(rememberedPlace("site", undefined, s)).toEqual({ free: { fx: 0.5, fy: 1 } });
    expect(rememberKey("x")).toContain("x");
  });

  it("remembers nothing with remember: off", () => {
    const session = new MemoryStorage();
    rememberPlace("off", "a", { anchor: "top-left" }, scope(session));
    expect(session.data.size).toBe(0);
  });

  it("survives storage that throws or holds garbage", () => {
    const throwing = {
      get sessionStorage(): Storage {
        throw new Error("SecurityError");
      },
    } as unknown as typeof globalThis;
    expect(() => rememberPlace("tab", "a", { anchor: "top-left" }, throwing)).not.toThrow();
    expect(rememberedPlace("tab", "a", throwing)).toBeNull();

    const full = {
      sessionStorage: {
        getItem: () => {
          throw new Error("no");
        },
        setItem: () => {
          throw new Error("QuotaExceededError");
        },
      },
    } as unknown as typeof globalThis;
    expect(() => rememberPlace("tab", "a", { anchor: "top-left" }, full)).not.toThrow();
    expect(rememberedPlace("tab", "a", full)).toBeNull();

    const s = new MemoryStorage();
    s.setItem(rememberKey("a"), "{not json");
    expect(rememberedPlace("tab", "a", scope(s))).toBeNull();
    s.setItem(rememberKey("a"), JSON.stringify({ anchor: "nowhere" }));
    expect(rememberedPlace("tab", "a", scope(s))).toBeNull();
  });
});

function controller(over: Partial<PlacementOptions> = {}, s = scope()) {
  const c = new PlacementController({
    anchor: "bottom-right",
    move: "snap",
    remember: "tab",
    offset: 16,
    topClear: 0,
    agent: "a",
    scope: s,
    ...over,
  });
  c.layout(size, view);
  return c;
}

describe("PlacementController", () => {
  it("starts at the configured anchor", () => {
    expect(controller().getSnapshot()).toMatchObject({ anchor: "bottom-right", free: false });
  });

  it("snaps a drag to the nearest anchor and remembers it", () => {
    const s = scope();
    const c = controller({}, s);
    const start = c.getSnapshot().point;
    expect(c.startDrag({ x: start.x + 10, y: start.y + 10 })).toBe(true);
    c.drag({ x: 40, y: 40 });
    expect(c.getSnapshot().dragging).toBe(true);
    c.endDrag();
    expect(c.getSnapshot()).toMatchObject({ anchor: "top-left", point: { x: 16, y: 16 }, dragging: false });
    expect(controller({}, s).getSnapshot().anchor).toBe("top-left");
  });

  it("leaves a free drag where it was dropped, clamped, and restores it", () => {
    const s = scope();
    const c = controller({ move: "free" }, s);
    const start = c.getSnapshot().point;
    c.startDrag(start);
    c.drag({ x: 400, y: 300 });
    c.endDrag();
    expect(c.getSnapshot()).toMatchObject({ point: { x: 400, y: 300 }, free: true });
    c.startDrag({ x: 400, y: 300 });
    c.drag({ x: -500, y: 5000 });
    c.endDrag();
    expect(c.getSnapshot().point).toEqual({ x: 16, y: 800 - 16 - 100 });
    const again = controller({ move: "free" }, s);
    expect(again.getSnapshot().free).toBe(true);
  });

  it("only snaps on touch screens", () => {
    const c = controller({ move: "free", touch: true });
    const start = c.getSnapshot().point;
    c.startDrag(start);
    c.drag({ x: 400, y: 300 });
    c.endDrag();
    expect(c.getSnapshot().free).toBe(false);
  });

  it("does not move when fixed, and ignores a remembered place", () => {
    const s = scope();
    rememberPlace("tab", "a", { anchor: "top-left" }, s);
    const c = controller({ move: "fixed" }, s);
    expect(c.getSnapshot().anchor).toBe("bottom-right");
    expect(c.startDrag({ x: 0, y: 0 })).toBe(false);
  });

  it("keeps clear of avoided rectangles on layout", () => {
    const c = controller();
    c.layout(size, view, [{ left: 0, top: 740, width: 1200, height: 60 }]);
    expect(c.getSnapshot().point.y).toBe(740 - 16 - 100);
  });
});
