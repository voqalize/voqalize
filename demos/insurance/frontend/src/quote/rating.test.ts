import { describe, expect, it } from "vitest";
import type { ProductId } from "../data/types";
import { quote } from "./rating";

const glob = import.meta.glob("../../../data/quote_cases.json", { eager: true });
const file = Object.values(glob)[0] as { default?: unknown } | undefined;
const data = (file?.default ?? file) as
  | {
      cases: {
        product: ProductId;
        answers: Record<string, string>;
        addons: string[] | null;
        expected: Record<string, unknown>;
      }[];
    }
  | undefined;

describe.skipIf(!data)("rating.ts against data/quote_cases.json (written by backend/rating.py)", () => {
  for (const [i, c] of (data?.cases ?? []).entries()) {
    it(`case ${i}: ${c.product} ${c.expected.complete ? `total ${c.expected.total}` : (c.expected.error ?? `missing ${(c.expected.missing as string[]).join(", ")}`)}`, () => {
      const q = quote(c.product, c.answers, c.addons);
      const e = c.expected;
      expect(q.complete).toBe(e.complete);
      expect(q.missing).toEqual(e.missing);
      expect(q.lines).toEqual(e.lines);
      expect(q.net).toBe(e.net);
      expect(q.gst_percent).toBe(e.gst_percent);
      expect(q.gst).toBe(e.gst);
      expect(q.total).toBe(e.total);
      expect(q.idv).toBe(e.idv);
      expect(q.unavailable).toEqual(e.unavailable ?? {});
      expect(q.error).toBe(e.error);
    });
  }
});

describe("rating basics", () => {
  it("lists what is missing and stays incomplete", () => {
    const q = quote("car", { vehicle_class: "suv" });
    expect(q.complete).toBe(false);
    expect(q.missing).toContain("fuel");
    expect(q.missing).not.toContain("voluntary_deductible");
  });
  it("omits a zero discount line", () => {
    const q = quote("travel", { region: "asia", trip_days: "5", travellers: "1", eldest_age: "30" });
    expect(q.lines.map((l) => l.id)).toEqual(["base"]);
  });
});
