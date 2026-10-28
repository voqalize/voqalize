/**
 * A spec declared once: every move's argument type comes from its declaration,
 * and registering takes the class and a cue's argument names from it.
 */

import { describe, expect, expectTypeOf, it } from "vitest";

import { attachStage } from "../src/attach";
import { Moves } from "../src/moves";
import { type ArgsOf, defineScene, type EventData, type SliceOf } from "../src/scene";
import { Spotlight } from "../src/spotlight";

const scene = defineScene({
  stage: 1,
  id: "shop",
  moves: [
    { id: "core.show", verb: "show", class: "look", args: [{ name: "target" }], say: "{show: Heading}" },
    {
      id: "shop.filter",
      class: "reversible",
      args: [
        { name: "category_path" },
        { name: "size", type: "array", optional: true },
        { name: "sort", enum: ["price_asc", "price_desc"], optional: true },
        { name: "qty", type: "integer", default: 1 },
        { name: "tabs", type: "array", items: { enum: ["fotos", "specs"] } },
        { name: "open", type: "boolean", optional: true },
      ],
    },
    { id: "shop.checkout", class: "confirmed" },
  ],
});

type S = typeof scene.spec;

describe("defineScene", () => {
  it("infers each move's arguments from its declaration", () => {
    expectTypeOf<ArgsOf<S, "core.show">>().toEqualTypeOf<{ target: string }>();
    expectTypeOf<ArgsOf<S, "shop.filter">>().toEqualTypeOf<{
      category_path: string;
      tabs: ("fotos" | "specs")[];
      size?: string[] | null;
      sort?: "price_asc" | "price_desc" | null;
      qty?: number;
      open?: boolean | null;
    }>();
    expectTypeOf<ArgsOf<S, "shop.checkout">>().toEqualTypeOf<Record<never, never>>();
  });

  it("registers with the declared class, and a cue's argument names", () => {
    const moves = new Moves(new Spotlight({ color: "#000" }));
    scene.register(moves, "core.show", async (a) => `showed ${a.target}`);
    scene.register(moves, "shop.filter", async (a) => `filtered ${a.category_path}`);
    expect(moves.classOf("core.show")).toBe("look");
    expect(moves.classOf("shop.filter")).toBe("reversible");
    // @ts-expect-error: a move the spec does not declare
    expect(() => scene.register(moves, "shop.nope", async () => null)).toThrow(/declares no move shop.nope/);
  });

  it("registerAll wants a performer for every move", () => {
    const moves = new Moves(new Spotlight({ color: "#000" }));
    scene.registerAll(moves, {
      "core.show": async () => null,
      "shop.filter": async () => null,
      "shop.checkout": async () => null,
    });
    expect(moves.ids.sort()).toEqual(["core.show", "shop.checkout", "shop.filter"]);
    // @ts-expect-error: shop.checkout has no performer
    scene.registerAll(moves, { "core.show": async () => null, "shop.filter": async () => null });
  });

  it("refuses one id twice", () => {
    expect(() =>
      defineScene({
        stage: 1,
        id: "x",
        moves: [
          { id: "a.b", class: "look" },
          { id: "a.b", class: "look" },
        ],
      }),
    ).toThrow(/two moves have the id a.b/);
  });
});

const shop = defineScene({
  stage: 1,
  id: "shop",
  moves: [{ id: "cart.add", class: "confirmed", args: [{ name: "path" }] }],
  slices: [
    {
      id: "cart",
      fields: [
        { name: "count", type: "integer" },
        { name: "items", type: "array", fields: [{ name: "name" }, { name: "gift_note", private: true }] },
        { name: "email", private: true },
        { name: "subtotal", type: "number", optional: true },
      ],
    },
  ],
  events: [
    { id: "cart.changed", slice: "cart", op: "set", note: "{by} changed the cart" },
    { id: "cart.counted", slice: "cart" },
    { id: "cart.emptied", slice: "cart", op: "clear" },
  ],
});

type Shop = typeof shop.spec;

describe("state events", () => {
  it("types an event's data from its slice, private fields left out", () => {
    expectTypeOf<SliceOf<Shop, "cart">>().toEqualTypeOf<{
      count: number;
      items: { name: string }[];
      subtotal?: number | null;
    }>();
    expectTypeOf<EventData<Shop, "cart.counted">>().toEqualTypeOf<Partial<SliceOf<Shop, "cart">>>();
    expectTypeOf<EventData<Shop, "cart.emptied">>().toEqualTypeOf<Record<never, never>>();
  });

  it("sends only the declared, public fields, whatever it was handed", () => {
    const leaky = { count: 1, items: [{ name: "Toalla", gift_note: "para mamá" }], email: "a@b.c", extra: 1 };
    const ev = shop.event("cart.changed", leaky as never, { by: "agent", callRef: "c4" });
    expect(ev).toEqual({ name: "cart.changed", by: "agent", call_ref: "c4", data: { count: 1, items: [{ name: "Toalla" }] } });
    expect(shop.event("cart.emptied", {})).toEqual({ name: "cart.emptied", by: "visitor", data: {} });
    // @ts-expect-error: not a declared event
    expect(() => shop.event("cart.exploded", {})).toThrow(/declares no event/);
  });

  it("rides the page's ui-event as stage_event", () => {
    const sent: [string, unknown][] = [];
    const client = { on() {}, off() {}, sendUIEvent: (e: string, p?: unknown) => sent.push([e, p]) };
    const att = attachStage(client, { onCue() {}, onMove() {} });
    att.send(shop.event("cart.counted", { count: 2 }));
    expect(sent).toEqual([["stage_event", { name: "cart.counted", by: "visitor", data: { count: 2 } }]]);
    att.detach();
  });
});
