import { describe, expect, it } from "vitest";
import { advise, answer, nextQuestion, sizedProducts } from "./finder";

describe("size finder", () => {
  it("asks what is being sized first", () => {
    expect(nextQuestion({})?.id).toBe("kind");
  });
  it("a queen mattress picks Queen", () => {
    const a = answer(answer({}, "kind", "bed"), "mattress", "queen");
    expect(nextQuestion(a)).toBeNull();
    expect(advise(a)?.size).toBe("Queen");
  });
  it("no mattress asks sleepers then room, and two in a roomy room is King", () => {
    let a = answer(answer({}, "kind", "bed"), "mattress", "none");
    expect(nextQuestion(a)?.id).toBe("sleepers");
    a = answer(a, "sleepers", "two");
    expect(nextQuestion(a)?.id).toBe("room");
    expect(advise(answer(a, "room", "roomy"))?.size).toBe("King");
    expect(advise(answer(a, "room", "snug"))?.size).toBe("Queen");
  });
  it("a new kind clears the answers under it", () => {
    const a = answer(answer(answer({}, "kind", "bed"), "mattress", "king"), "kind", "vase");
    expect(a).toEqual({ kind: "vase" });
    expect(advise(answer(a, "place", "dining_table"))?.size).toBe("Large");
  });
  it("a changed mattress drops sleepers and room", () => {
    let a = answer(answer(answer({}, "kind", "bed"), "mattress", "none"), "sleepers", "two");
    a = answer(a, "mattress", "king");
    expect(a).toEqual({ kind: "bed", mattress: "king" });
  });
  it("rugs advise without a size", () => {
    const r = advise(answer(answer({}, "kind", "rug"), "layout", "front_legs"));
    expect(r?.size).toBeNull();
    expect(r?.section).toBe("rugs");
  });
  it("sized beds come in the picked size", () => {
    const beds = sizedProducts("beds", "King");
    expect(beds.length).toBe(9);
    expect(beds.every(({ v }) => v.options.Size === "King")).toBe(true);
    expect(sizedProducts("vases", "Small").length).toBe(49);
  });
});
