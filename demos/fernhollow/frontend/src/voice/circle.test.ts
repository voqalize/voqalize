/**
 * Circle to ask: which boxes a loop holds, in which order, and the events the
 * selection sends (CONTRACT.md v3).
 */
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { type Box, type Point, type Thing, coverage, inside, smoothPath, thingsInLoop, useSelection } from "./circle";
import { setEventSender } from "./events";

/** A loop round a rectangle, as a hand would draw it: 40 points on an ellipse. */
function ellipse(cx: number, cy: number, rx: number, ry: number, n = 40): Point[] {
  return Array.from({ length: n }, (_, i) => ({ x: cx + Math.cos((i / n) * 2 * Math.PI) * rx, y: cy + Math.sin((i / n) * 2 * Math.PI) * ry }));
}
const card = (id: string, left: number, top: number, w = 100, h = 120): { thing: Thing; box: Box } => ({
  thing: { kind: "product", id },
  box: { left, top, width: w, height: h },
});

let sent: [string, unknown][] = [];
beforeAll(() => setEventSender((event, payload) => sent.push([event, payload])));
beforeEach(() => {
  sent = [];
  useSelection.setState({ things: [], page: "" });
});

describe("the loop's geometry", () => {
  it("knows inside from outside", () => {
    const loop = ellipse(100, 100, 50, 50);
    expect(inside({ x: 100, y: 100 }, loop)).toBe(true);
    expect(inside({ x: 160, y: 100 }, loop)).toBe(false);
  });

  it("measures how much of a box the loop holds", () => {
    const loop = ellipse(100, 100, 200, 200);
    expect(coverage({ left: 50, top: 50, width: 100, height: 100 }, loop)).toBe(1);
    // A box half across the loop's left edge (a rectangle loop, to make the half exact).
    const rect: Point[] = [
      { x: 0, y: 0 },
      { x: 200, y: 0 },
      { x: 200, y: 200 },
      { x: 0, y: 200 },
    ];
    // Half across: 4 of the 7 sample columns fall inside.
    expect(coverage({ left: -70, top: 50, width: 140, height: 100 }, rect)).toBeCloseTo(4 / 7, 5);
    expect(coverage({ left: -100, top: 50, width: 140, height: 100 }, rect)).toBeLessThan(0.5);
    expect(coverage({ left: 300, top: 50, width: 100, height: 100 }, rect)).toBe(0);
  });
});

describe("thingsInLoop", () => {
  const grid = [card("a", 0, 0), card("b", 120, 0), card("c", 240, 0), card("d", 0, 160), card("e", 120, 160)];

  it("takes what is at least half inside, in reading order", () => {
    // Round the top row's first two and the second row's first.
    const loop = ellipse(110, 140, 170, 170);
    const got = thingsInLoop(loop, [...grid].reverse()).map((t) => t.id);
    expect(got).toEqual(["a", "b", "d", "e"]);
  });

  it("leaves a box that is mostly outside", () => {
    const loop = ellipse(60, 60, 90, 90);
    expect(thingsInLoop(loop, grid).map((t) => t.id)).toEqual(["a"]);
  });

  it("counts a thing once, and takes at most eight", () => {
    const many = Array.from({ length: 12 }, (_, i) => card(`p${i}`, (i % 6) * 110, Math.floor(i / 6) * 130));
    const loop = ellipse(330, 130, 700, 400);
    const got = thingsInLoop(loop, [...many, card("p0", 0, 0)]);
    expect(got).toHaveLength(8);
    expect(new Set(got.map((t) => t.id)).size).toBe(8);
    expect(got[0].id).toBe("p0");
  });

  it("draws a smooth path", () => {
    expect(smoothPath([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }])).toMatch(/^M0\.0,0\.0 Q10\.0,0\.0 10\.0,5\.0 L10\.0,10\.0$/);
  });
});

describe("the selection's events", () => {
  it("sends selection with the things, the gesture and the page", () => {
    const things: Thing[] = [
      { kind: "product", id: "weathered-oak-dining-table" },
      { kind: "room", id: "dining" },
    ];
    useSelection.getState().select(things, "/");
    expect(sent).toEqual([["selection", { things, gesture: "circle", page: "/", by: "visitor" }]]);
  });

  it("a new circle clears the last one first", () => {
    useSelection.getState().select([{ kind: "product", id: "a" }], "/");
    sent = [];
    useSelection.getState().select([{ kind: "category", id: "sofas" }], "/shop");
    expect(sent.map(([e]) => e)).toEqual(["selection_cleared", "selection"]);
    expect(sent[0][1]).toEqual({ by: "visitor" });
  });

  it("the shopper's clear sends selection_cleared; Emily's clear_selection does not echo", () => {
    useSelection.getState().select([{ kind: "product", id: "a" }], "/");
    sent = [];
    useSelection.getState().clear();
    expect(sent).toEqual([["selection_cleared", { by: "visitor" }]]);
    useSelection.getState().select([{ kind: "product", id: "a" }], "/");
    sent = [];
    useSelection.getState().clear("emily");
    expect(sent).toEqual([]);
    expect(useSelection.getState().things).toEqual([]);
  });
});
