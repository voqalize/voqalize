/**
 * A spec declared once: every move's argument type comes from its declaration,
 * and registering takes the class and a cue's argument names from it.
 */

import { describe, expect, expectTypeOf, it } from "vitest";

import { Moves } from "../src/moves";
import { type ArgsOf, defineScene } from "../src/scene";
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
