/** The page's pricing and calendar agree with the brain's, case by case. */
import { describe, expect, it } from "vitest";
import pricingCases from "../../../content/pricing_cases.json";
import calendarCases from "../../../content/calendar_cases.json";
import { businessDays, reference, slotById, slotsOn } from "./calendar";
import { quote, type Billing } from "./pricing";

describe("pricing twin", () => {
  for (const c of pricingCases.cases) {
    it(`${c.input.headcount} employees, ${c.input.modules.join("+") || "core"}, ${c.input.billing}${c.input.filing ? ", filing" : ""}`, () => {
      const q = quote({ ...c.input, billing: c.input.billing as Billing }) as unknown as Record<string, unknown>;
      for (const [k, v] of Object.entries(c.expect)) expect(q[k], k).toEqual(v);
      expect((q.lines as { key: string }[]).map((l) => l.key)).toEqual(c.lines);
    });
  }
  it("56 employees with reimbursements is Growth at ₹6,664 a month before GST", () => {
    const q = quote({ headcount: 56, modules: ["reimbursements"], billing: "monthly", filing: false });
    expect(q.plan).toBe("growth");
    expect(q.monthly).toBe(6664);
  });
});

describe("calendar twin", () => {
  for (const c of calendarCases.cases) {
    it(`days and slots after ${c.today}`, () => {
      expect(businessDays(c.today)).toEqual(c.days);
      for (const [day, slots] of Object.entries(c.slots)) {
        expect(slotsOn(day).map((s) => [s.time, s.rep, s.taken])).toEqual(slots);
      }
    });
  }
  it("builds the reference from the slot", () => {
    const ex = calendarCases.reference_example;
    expect(reference(slotById(ex.slot)!)).toBe(ex.reference);
  });
});
