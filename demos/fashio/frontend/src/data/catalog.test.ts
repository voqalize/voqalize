import { beforeAll, describe, expect, it } from "vitest";
import raw from "../../../data/catalog.json";
import { type CatalogIndex, facet, filtersFromRoute, getProduct, routeFor, search, setIndex, sizeLabel, summarise } from "./catalog";

beforeAll(() => {
  setIndex(raw as unknown as CatalogIndex);
});

describe("the catalogue search (CONTRACT.md, Search)", () => {
  it("filters women's kurtas under ₹2,000 with M in stock, popular first", () => {
    const xs = search({ dept: "women", types: ["kurtas"], sizes: ["M"], price_max: 2000 });
    expect(xs.length).toBeGreaterThan(0);
    for (const p of xs) {
      expect(["women", "unisex"]).toContain(p.gender);
      expect(p.type).toBe("kurtas");
      expect(p.price).toBeLessThanOrEqual(2000);
      expect(p.sizes.some(([l, n]) => l === "M" && n > 0)).toBe(true);
    }
    expect(xs.map((p) => p.rank)).toEqual([...xs.map((p) => p.rank)].sort((a, b) => a - b));
    // 7412 is a women's kurta with M out of stock: never in this result.
    expect(xs.some((p) => p.id === 7412)).toBe(false);
  });

  it("sorts by price and needs every query word", () => {
    const xs = search({ query: "pink kurta", sort: "price_asc" });
    expect(xs.length).toBeGreaterThan(0);
    for (let i = 1; i < xs.length; i++) expect(xs[i].price).toBeGreaterThanOrEqual(xs[i - 1].price);
    expect(xs.some((p) => p.id === 7412)).toBe(true);
  });

  it("says the search in one line", () => {
    expect(summarise({})).toBe("everything");
    expect(summarise({ dept: "women", types: ["kurtas"], price_max: 2000, sort: "price_asc" })).toBe("Women, Kurtas, under ₹2,000; price low to high");
  });

  it("facets ignore their own filter", () => {
    const brands = facet("brands", { dept: "women", types: ["kurtas"], brands: ["W"] });
    expect(brands.length).toBeGreaterThan(1);
  });

  it("maps a search to its route and back", () => {
    expect(routeFor({ dept: "women", types: ["kurtas"], brands: ["W"] })).toBe("/shop/women/kurtas");
    expect(routeFor({ types: ["kurtas"] })).toBe("/shop");
    expect(routeFor({ dept: "men", query: "white shirt" })).toBe("/shop/men?q=white%20shirt");
    expect(filtersFromRoute("women", "kurtas")).toEqual({ dept: "women", types: ["kurtas"] });
    expect(filtersFromRoute("nowhere", "kurtas")).toEqual({});
  });

  it("reads a size the way a shopper says it", () => {
    expect(sizeLabel(getProduct(14395)!, "7")).toBe("UK 7");
    expect(sizeLabel(getProduct(7412)!, "xl")).toBe("XL");
    expect(sizeLabel(getProduct(4664)!, "one size")).toBe("Onesize");
  });
});
