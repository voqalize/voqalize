import { describe, expect, it } from "vitest";
import { Moves, Spotlight } from "@voqalize/stage";
import { checkRegistry } from "@voqalize/stage/conformance";
import { scene } from "./scene.gen";
import { registerMoves } from "./performers";

describe("Stage registry", () => {
  it("every move the spec declares has a performer, under its class", () => {
    const moves = new Moves(new Spotlight({ color: "#0B6E5F" }));
    registerMoves(moves);
    expect(checkRegistry(scene, moves)).toEqual([]);
    expect(moves.ids.length).toBe(scene.spec.moves.length);
    expect(moves.ids.length).toBe(19);
  });
});
