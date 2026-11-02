/** Orders saved by an earlier build must be upgraded, never crash the returns desk. */
import { describe, expect, it } from "vitest";
import { ordersKnown, normalizeOrder } from "./orders";

const legacy = (number: string, placedAt: string) => ({
  number,
  placedAt,
  lines: [{ product_id: "sand-linen-sofa-with-deep-seat", variant_id: "nope", qty: 1 }],
  subtotal: 1395,
  saved: 0,
  delivery: 0,
  address: { email: "sam.rivera@example.com", first_name: "Sam", last_name: "Rivera" },
});

describe("orders saved before v4", () => {
  it("are upgraded to the contract shape", () => {
    const o = normalizeOrder(legacy("FH-879106", "2026-11-02T18:24:00.000Z"));
    expect(o).toMatchObject({
      number: "FH-879106",
      email: "sam.rivera@example.com",
      name: "Sam Rivera",
      placed_at: "2026-11-02T18:24:00.000Z",
      total: 1395,
      status: "delivered",
    });
    expect(o?.lines[0]).toMatchObject({ product_id: "sand-linen-sofa-with-deep-seat", qty: 1 });
    expect(o?.lines[0]?.title).toBeTruthy();
  });

  it("sort for orders_known even with two of them (the comparator that crashed)", () => {
    const orders = [legacy("FH-1", "2026-11-01T10:00:00.000Z"), legacy("FH-2", "2026-11-02T10:00:00.000Z")]
      .map(normalizeOrder)
      .filter((o) => o !== null);
    expect(() => ordersKnown(orders)).not.toThrow();
    expect(ordersKnown(orders).map((o) => o.number)).toEqual(["FH-2", "FH-1"]);
  });

  it("junk is dropped, a missing date does not throw", () => {
    expect(normalizeOrder(null)).toBeNull();
    expect(normalizeOrder({ number: 7 })).toBeNull();
    const undated = normalizeOrder({ number: "FH-3", lines: [] });
    expect(undated?.placed_at).toBe(new Date(0).toISOString());
  });
});
