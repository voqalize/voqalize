/**
 * The app's rules give the brain's answers: data/rules_cases.json is written by
 * the brain's `hotel.write_cases()` (and held current by test_belmonte_e2e.py).
 */
import { describe, expect, it } from "vitest";
import cases from "../../../data/rules_cases.json";
import type { Outlet, ScenarioId } from "../data";
import { assignRoom, clockOf, meetingQuote, orderTotals, spaSlots } from "./rules";

describe("the app's rules match the brain's", () => {
  it("order totals", () => {
    for (const c of cases.orders) expect(orderTotals(c.outlet as Outlet, c.lines, c.tip)).toEqual(c.totals);
  });
  it("spa free times", () => {
    for (const c of cases.spa) expect(spaSlots(clockOf(c.scenario as ScenarioId), c.treatment, c.date, c.pref)).toEqual(c.slots);
  });
  it("room assignment", () => {
    for (const c of cases.rooms) expect(assignRoom(c.floor, c.bed, c.quiet).room).toBe(c.room);
  });
  it("meeting quotes", () => {
    for (const c of cases.quotes) expect(meetingQuote(c.room, c.block, c.hours, c.headcount, c.catering, c.av)).toEqual(c.quote);
  });
});
