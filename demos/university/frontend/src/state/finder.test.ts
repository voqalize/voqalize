import { beforeEach, describe, expect, it } from "vitest";
import { facetByName, resolveFacet, resolveOption, resolveProgram } from "../data/catalogue";
import { filterLabels, listed, matching, useFinder } from "./finder";

describe("programme finder", () => {
  beforeEach(() => {
    useFinder.getState().clear();
    useFinder.getState().setPicks([]);
  });

  it("ORs within a facet and ANDs across facets", () => {
    const f = useFinder.getState();
    f.setOption("Level", "pg", true);
    const pg = matching(useFinder.getState().filters);
    expect(pg.every((p) => p.level === "pg")).toBe(true);
    f.setOption("Mode", "online", true);
    const pgOnline = matching(useFinder.getState().filters);
    expect(pgOnline.map((p) => p.id).sort()).toEqual(["online-mba", "online-mca", "online-mcom"]);
    f.setOption("Level", "diploma", true);
    expect(matching(useFinder.getState().filters).map((p) => p.id)).toContain("pgd-data-analytics");
    expect(filterLabels(useFinder.getState().filters)).toEqual(["Level: Postgraduate", "Level: Diploma", "Mode: Online"]);
  });

  it("sorts by fee a year, low to high, and pins hidden picks on top", () => {
    const f = useFinder.getState();
    f.setOption("Level", "pg", true);
    f.setOption("Mode", "online", true);
    f.setPicks(["online-mba", "pgd-data-analytics"]);
    const { pinned, results } = listed(useFinder.getState());
    expect(results.map((p) => p.fee_per_year)).toEqual([...results.map((p) => p.fee_per_year)].sort((a, b) => a - b));
    expect(pinned.map((p) => p.id)).toEqual(["pgd-data-analytics"]);
  });

  it("matches said facets, options and programmes loosely", () => {
    expect(resolveFacet("fees")?.name).toBe("Fee");
    expect(resolveOption(facetByName("Level"), "PG")?.id).toBe("pg");
    expect(resolveOption(facetByName("Level"), "postgraduate")?.id).toBe("pg");
    expect(resolveOption(facetByName("Fee"), "1-2 lakh")?.id).toBe("1l_2l");
    expect(resolveOption(facetByName("Fee"), "₹1–2 lakh")?.id).toBe("1l_2l");
    expect(resolveOption(facetByName("Hours"), "up to 8 hours a week")?.id).toBe("upto_8");
    expect(resolveOption(facetByName("Campus"), "Bangalore")?.id).toBe("bengaluru");
    expect(resolveProgram("Online MBA")?.id).toBe("online-mba");
    expect(resolveProgram("btech-cse")?.id).toBe("btech-cse");
  });
});
