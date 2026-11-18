import { describe, expect, it } from "vitest";
import { moves } from "./host";
import { registerPerformers } from "./performers";

registerPerformers();

describe("performers", () => {
  it("registers every move of the scene", () => {
    expect(moves.ids.sort()).toEqual(
      ["apply.fill", "apply.next", "apply.step", "catalogue.clear", "catalogue.compare", "catalogue.filter", "catalogue.pick", "site.go", "site.open", "site.show"].sort(),
    );
  });

  it("refuses a filter value with the facet's options instead of guessing", async () => {
    const r = await moves.run("catalogue.filter", { facet: "Level", value: "PhD" }, "t-1");
    expect(r?.outcome).toBe("refused");
    expect(r?.refused?.[0]).toMatchObject({ arg: "value", options: ["Undergraduate", "Postgraduate", "Diploma", "Certificate"] });
  });

  it("refuses an unknown facet with the facets", async () => {
    const r = await moves.run("catalogue.filter", { facet: "Colour", value: "Blue" }, "t-2");
    expect(r?.outcome).toBe("refused");
    expect(r?.refused?.[0]?.options).toEqual(["Level", "School", "Mode", "Campus", "Fee", "Hours"]);
  });

  it("refuses a pick that is not in the catalogue", async () => {
    const r = await moves.run("catalogue.pick", { first: "mba", second: "phd-astrophysics" }, "t-3");
    expect(r?.outcome).toBe("refused");
    expect(r?.refused?.[0]?.arg).toBe("second");
  });

  it("refuses an unknown field of the application", async () => {
    const r = await moves.run("apply.fill", { field: "blood_group", value: "O+" }, "t-4");
    expect(r?.outcome).toBe("refused");
    expect(r?.refused?.[0]?.options).toContain("class12_percent");
  });
});
