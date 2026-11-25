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
  const moves = new Moves(new Spotlight({ color: "#b8873e" }));
  scene.registerAll(moves, performers);

  it("cover the spec", () => {
    expect(checkRegistry(scene, moves).filter((f) => f.level === "error")).toEqual([]);
  });

  it("refuse an unknown treatment with the ones on offer", async () => {
    const r = await moves.run("spa.treatment", { treatment_id: "mud-bath" }, "t1");
    expect(r?.outcome).toBe("refused");
    expect(r?.refused?.[0]?.options).toContain("swedish-50");
  });

  it("refuse a sold-out late check-out with the ones still free", async () => {
    const r = await moves.run("late.pick", { time: "16:00" }, "t2");
    expect(r?.outcome).toBe("refused");
    expect(r?.refused?.[0]?.options).toEqual(["12:00", "13:00", "14:00"]);
  });

  it("refuse preferences before the guest has scanned their ID", async () => {
    const r = await moves.run("checkin.prefs", { floor: "high" }, "t3");
    expect(r?.outcome).toBe("refused");
  });
});
