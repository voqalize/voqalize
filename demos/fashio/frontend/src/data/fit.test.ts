import { beforeAll, describe, expect, it } from "vitest";
import raw from "../../../data/catalog.json";
import { type CatalogIndex, getProduct, setIndex } from "./catalog";
import { recommend } from "./fit";

beforeAll(() => {
  setIndex(raw as unknown as CatalogIndex);
});

describe("Find my size (CONTRACT.md, Fit)", () => {
  it("swaps an out-of-stock pick for the nearest size in stock", () => {
    // 7412: XS 0, S 12, M 0, L 0, XL 13. M is out; S is one step down, XL two up.
    const a = recommend(getProduct(7412)!, { usual_size: "M", fit: "regular", height_cm: 165 });
    expect(a).toMatchObject({ size: "S", wanted: "M", steps: 0 });
  });

  it("keeps the usual size when it is in stock", () => {
    expect(recommend(getProduct(7411)!, { usual_size: "M" })).toMatchObject({ size: "M", steps: 0 });
  });

  it("converts a letter to a waist for trousers", () => {
    // 11286 Wrangler jeans: 28, 30 (0), 32 (1), 34, 36, 38 (0). Men's M is a 32.
    expect(recommend(getProduct(11286)!, { usual_size: "M" })).toMatchObject({ size: "32" });
  });

  it("reads a bare number as a UK shoe size", () => {
    // 14395 flats: UK 3, 4, 5 (0), 6 (0), 7. A 5 goes to the nearest in stock, a tie to the larger.
    const a = recommend(getProduct(14395)!, { usual_size: "5" });
    expect(a?.wanted).toBe("UK 5");
    expect(a?.size).toBe("UK 4");
  });

  it("has nothing to say for one-size products", () => {
    expect(recommend(getProduct(4664)!, { usual_size: "M" })).toBeNull();
  });
});
