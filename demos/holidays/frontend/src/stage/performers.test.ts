/**
 * Every move the spec declares has a performer under its declared class, and
 * the ones that refuse do so with options instead of guessing.
 */
import { Moves, Spotlight } from "@voqalize/stage";
import { checkRegistry } from "@voqalize/stage/conformance";
import { describe, expect, it } from "vitest";
import { performers } from "./performers";
import { scene } from "./scene.gen";

describe("performers", () => {
  const moves = new Moves(new Spotlight({ color: "#e8913a" }));
  scene.registerAll(moves, performers);

  it("cover the spec", () => {
    expect(checkRegistry(scene, moves).filter((f) => f.level === "error")).toEqual([]);
  });

  it("refuse an unknown destination with the ones on offer", async () => {
    const r = await moves.run("trip.brief", { destination: "atlantis" }, "t1");
    expect(r?.outcome).toBe("refused");
    expect(r?.refused?.[0]?.options).toContain("bali");
  });

  it("refuse a flight before the trip has cities", async () => {
    const r = await moves.run("trip.flight", { flight_id: "DEL-bali-1" }, "t2");
    expect(r?.outcome).toBe("refused");
  });
});
