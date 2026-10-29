/** Who made a change the page shows: the agent while its move acts and just
 *  after, the visitor otherwise. */

import { afterEach, describe, expect, it, vi } from "vitest";

import { AGENT_WINDOW_MS, Moves } from "../src/moves";
import { Spotlight } from "../src/spotlight";

afterEach(() => vi.useRealTimers());

describe("Moves.author", () => {
  it("is the agent's move while it acts and for a moment after, then the visitor's", async () => {
    vi.useFakeTimers();
    const moves = new Moves(new Spotlight({ color: "#000" }));
    const during: ReturnType<Moves["author"]>[] = [];
    moves.register("listing.sort", "reversible", async () => {
      during.push(moves.author());
      return "sorted";
    });
    expect(moves.author()).toEqual({ by: "visitor" });
    await moves.run("listing.sort", {}, "c7");
    expect(during).toEqual([{ by: "agent", callRef: "c7" }]);
    expect(moves.author()).toEqual({ by: "agent", callRef: "c7" });
    // Once the move is wholly done (its trailing rings included) and the
    // window has passed, a change is the visitor's.
    await vi.advanceTimersByTimeAsync(AGENT_WINDOW_MS * 10);
    expect(moves.author()).toEqual({ by: "visitor" });
  });
});
