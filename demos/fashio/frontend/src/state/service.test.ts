import { beforeAll, describe, expect, it } from "vitest";
import catalog from "../../../data/catalog.json";
import { type CatalogIndex, setIndex } from "../data/catalog";
import { giftReason, pickGifts } from "../data/gifts";
import { type Order, STORE, addDays, canCancel, returnCheck, returnRef, sampleOrders } from "../data/shop";
import { formReady, mergeOrders } from "./orders";
import { isEmptySearch, kioskSearch } from "./kiosk";

const TODAY = "2026-11-24";

beforeAll(() => {
  setIndex(catalog as unknown as CatalogIndex);
});

const byId = (id: string) => sampleOrders(TODAY).find((o) => o.id === id)!;

describe("orders merged with this browser", () => {
  it("puts orders placed here first and dates the samples from today", () => {
    const sample = sampleOrders(TODAY);
    const local: Order = { ...sample[0], id: "FSH-49001", placed: TODAY, status: "placed", local: true };
    const merged = mergeOrders(sample, [local], [], {}, TODAY);
    expect(merged[0].id).toBe("FSH-49001");
    expect(merged).toHaveLength(sample.length + 1);
    expect(merged.find((o) => o.id === "FSH-48213")!.delivered).toBe(addDays(TODAY, -3));
  });

  it("marks a cancelled order cancelled, with the refund in its timeline", () => {
    const merged = mergeOrders(sampleOrders(TODAY), [], ["FSH-48711"], {}, TODAY);
    const o = merged.find((x) => x.id === "FSH-48711")!;
    expect(o.status).toBe("cancelled");
    expect(o.cancelledHere).toBe(true);
    expect(o.eta).toBeUndefined();
    expect(o.events.at(-1)!.text).toMatch(/Refunded to your UPI/);
    expect(canCancel(o)).toBe(false);
  });

  it("flags only the returned item, and leaves the order delivered", () => {
    const ref = returnRef("FSH-48213", 7421);
    const merged = mergeOrders(sampleOrders(TODAY), [], [], { "FSH-48213|7421": ref }, TODAY);
    const o = merged.find((x) => x.id === "FSH-48213")!;
    expect(o.status).toBe("delivered");
    expect(o.items.find((i) => i.product_id === 7421)!.returnRef).toBe("RTN-48213-7421");
    expect(o.items.find((i) => i.product_id === 35301)!.returnRef).toBeUndefined();
  });
});

describe("cancel and return rules", () => {
  it("cancels only before dispatch", () => {
    expect(canCancel(byId("FSH-48711"))).toBe(true); // packed
    expect(canCancel(byId("FSH-48602"))).toBe(false); // shipped
    expect(canCancel(byId("FSH-48530"))).toBe(false); // out for delivery
    expect(canCancel(byId("FSH-48213"))).toBe(false); // delivered
  });

  it("returns within 7 days of delivery: -3 yes, -11 no", () => {
    const none = new Set<string>();
    const recent = returnCheck(byId("FSH-48213"), 7421, none, TODAY);
    expect(recent).toEqual({ ok: true, daysLeft: 4 });
    const old = returnCheck(byId("FSH-47920"), 3802, none, TODAY);
    expect(old.ok).toBe(false);
    expect(old.why).toMatch(/window closed/);
  });

  it("holds the day boundaries: day 7 is the last, day 8 is closed", () => {
    const o = byId("FSH-48213");
    const none = new Set<string>();
    expect(returnCheck({ ...o, delivered: addDays(TODAY, -7) }, 7421, none, TODAY)).toEqual({ ok: true, daysLeft: 0 });
    expect(returnCheck({ ...o, delivered: addDays(TODAY, -8) }, 7421, none, TODAY).ok).toBe(false);
  });

  it("never returns a fragrance, a repeat, or an undelivered order", () => {
    const o = byId("FSH-48090");
    expect(returnCheck(o, 36940, new Set(), TODAY)).toMatchObject({ ok: false, why: "Fragrances cannot be returned." });
    expect(returnCheck(o, 1889, new Set(), TODAY).ok).toBe(true);
    expect(returnCheck(o, 1889, new Set(["FSH-48090|1889"]), TODAY).ok).toBe(false);
    expect(returnCheck(byId("FSH-48602"), 18894, new Set(), TODAY).ok).toBe(false);
  });

  it("enables Submit return only with item, reason and both ticks", () => {
    const f = { order_id: "FSH-48213", product_id: 7421, reason: "size_small", unused: true, tags: false, reference: null };
    expect(formReady(f)).toBe(false);
    expect(formReady({ ...f, tags: true })).toBe(true);
    expect(formReady({ ...f, tags: true, reference: "RTN-48213-7421" })).toBe(false);
  });
});

describe("gift finder", () => {
  it("picks at most one per type, within budget, for the recipient's side", () => {
    const brief = { recipient: "Mom", occasion: "Diwali", budget_max: 1999, colours: ["Gold"] };
    const picks = pickGifts(brief);
    expect(picks.length).toBeGreaterThan(0);
    expect(picks.length).toBeLessThanOrEqual(6);
    expect(new Set(picks.map((p) => p.type)).size).toBe(picks.length);
    for (const p of picks) {
      expect(p.price).toBeLessThanOrEqual(1999);
      expect(["women", "unisex"]).toContain(p.gender);
      expect(STORE.gifts.ideas.women).toContain(p.type);
      // No size given: one-size products only.
      expect(p.scale).toBe("one");
      expect(giftReason(p, brief).length).toBeGreaterThan(4);
    }
  });

  it("offers sized products only in the size given", () => {
    const picks = pickGifts({ recipient: "Brother", size: "M" });
    for (const p of picks) if (p.scale !== "one") expect(p.sizes.some(([l, n]) => l === "M" && n > 0)).toBe(true);
  });
});

describe("kiosk search", () => {
  it("searches the whole catalogue by words and gender", () => {
    expect(isEmptySearch({})).toBe(true);
    const kurtas = kioskSearch({ query: "kurta", genders: ["women"] });
    expect(kurtas.length).toBeGreaterThan(0);
    expect(kurtas.every((p) => ["women", "unisex"].includes(p.gender))).toBe(true);
    const cheap = kioskSearch({ types: ["watches"], price_max: 999 });
    expect(cheap.every((p) => p.type === "watches" && p.price <= 999)).toBe(true);
  });
});
