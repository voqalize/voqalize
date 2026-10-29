/** Which events from a tab not in front still reach the agent. */

import { describe, expect, it } from "vitest";

import { takenFromAnyTab } from "../src/extension/protocol";

describe("takenFromAnyTab", () => {
  const anyTab = new Set(["stage_result", "prices_read", "cart.changed"]);

  it("takes an app event by its name and a state event by its spec id", () => {
    expect(takenFromAnyTab(anyTab, "prices_read", {})).toBe(true);
    expect(takenFromAnyTab(anyTab, "stage_event", { name: "cart.changed", data: {} })).toBe(true);
  });

  it("leaves the rest to the tab in front", () => {
    expect(takenFromAnyTab(anyTab, "listing_shown", {})).toBe(false);
    expect(takenFromAnyTab(anyTab, "stage_event", { name: "listing.filtered" })).toBe(false);
    expect(takenFromAnyTab(anyTab, "stage_event", null)).toBe(false);
  });
});
