/**
 * The page's engine against the brain's: every case in data/engine_cases.json
 * (written by backend/engine.py) built and priced here must come out the same,
 * to the rupee, so the agent and the screen never quote different numbers.
 */
import { describe, expect, it } from "vitest";
import cases from "../../data/engine_cases.json";
import { DESTINATIONS } from "./data";
import { type Brief, type Trip, days, defaultStartForMonth, emptyTrip, fromPrice, price, recommend, transfers } from "./engine";

interface Case {
  brief: Brief;
  package: { split: number[]; flight_id: string | null; hotels: Record<string, { hotel_id: string; room_id: string }>; activities: { day: number; activity_id: string }[] };
  price: Record<string, number>;
  transfers: { id: string; price: number }[];
  days: { n: number; city: string; kind: string; date: string | null }[];
  month_start: Record<string, string>;
}
const all = cases as unknown as { cases: Case[]; from_prices: Record<string, Record<string, number>> };

describe("engine matches the brain's", () => {
  for (const c of all.cases) {
    const name = `${c.brief.from_city} → ${c.brief.destination}, ${c.brief.nights}N, ${c.brief.style}`;
    it(name, () => {
      const t: Trip = { ...emptyTrip(), brief: { ...c.brief } };
      const rec = recommend(t);
      expect(rec.flight_id).toBe(c.package.flight_id);
      expect(rec.hotels).toEqual(c.package.hotels);
      expect(rec.activities).toEqual(c.package.activities);
      const built: Trip = { ...t, split: c.package.split, ...rec };
      const p = price(built);
      for (const [k, v] of Object.entries(c.price)) expect([k, p[k as keyof typeof p]]).toEqual([k, v]);
      expect(transfers(built).map((l) => ({ id: l.id, price: l.price }))).toEqual(c.transfers);
      expect(days(built).map((d) => ({ n: d.day, city: d.city.id, kind: d.kind, date: d.date }))).toEqual(c.days);
      for (const [m, iso] of Object.entries(c.month_start)) expect(defaultStartForMonth(Number(m), "2026-11-18")).toBe(iso);
    });
  }
  it("quotes the same 'from' price on every destination card", () => {
    for (const [origin, byDest] of Object.entries(all.from_prices)) {
      for (const d of DESTINATIONS) expect([origin, d.id, fromPrice(d, origin)]).toEqual([origin, d.id, byDest[d.id]]);
    }
  });
});
