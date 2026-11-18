import { describe, expect, it } from "vitest";
import fixtures from "../../../data/slot_fixtures.json";
import { DATA, rupees, service } from "./clinic";
import { Calendar, addDays, changeTerms, checkRule, clockAt, dated, mondayOf, nextOpenDay } from "./slots";

interface FixtureSlot {
  time: string;
  branch: string;
  dentist: string | null;
  chair: string | null;
  resource: string | null;
}
interface Case {
  service: string;
  branch: string | null;
  dentist: string | null;
  date: string;
  slots: FixtureSlot[];
}
const fx = fixtures as unknown as {
  now: string;
  cases: Case[];
  rct_plan: { first: { date: string; time: string; branch: string }; next: { date: string; time: string; branch: string }[] };
};
const clock = clockAt(new Date(fx.now));
const cal = new Calendar(clock);

describe("the slot engine reproduces backend/clinic.py", () => {
  it("reads now in Asia/Kolkata", () => {
    expect(clock).toMatchObject({ today: "2026-11-18", minute: 10 * 60 + 7 });
  });

  for (const c of fx.cases) {
    it(`${c.service} ${c.branch ?? "any branch"} ${c.dentist ?? "any dentist"} on ${c.date}`, () => {
      const got = cal
        .slots(service(c.service)!, c.date, { branch: c.branch, dentist: c.dentist })
        .map((s) => ({ time: s.time, branch: s.branch, dentist: s.dentist, chair: s.chair, resource: s.resource }));
      expect(got).toEqual(c.slots);
    });
  }

  it("plans a root canal's later sittings", () => {
    const rct = service("rct")!;
    const first = cal.nextDays(rct, { dentist: "dr-kavitha", start: addDays(clock.today, 5), days: 1 })[0][1][0];
    expect({ date: first.date, time: first.time, branch: first.branch }).toEqual(fx.rct_plan.first);
    const next = cal.planSittings(rct, first).map((s) => ({ date: s.date, time: s.time, branch: s.branch }));
    expect(next).toEqual(fx.rct_plan.next);
  });
});

describe("dates, rules and terms", () => {
  it("dates authored bookings against this week", () => {
    expect(mondayOf("2026-11-18")).toBe("2026-11-16");
    expect(nextOpenDay("2026-11-21")).toBe("2026-11-23");
    const a = dated(DATA.patient_appointments[0], "2026-11-18");
    expect(a.date).toBe("2026-11-23");
  });

  it("groups rupees the Indian way", () => {
    expect(rupees(125000)).toBe("₹1,25,000");
    expect(rupees(6500)).toBe("₹6,500");
    expect(rupees(300)).toBe("₹300");
  });

  it("checks the CBCT and OPG rules", () => {
    const [rohan, ishita, suresh] = DATA.patients;
    expect(checkRule(service("cbct")!, suresh, "2026-11-20", cal).ok).toBe(true);
    expect(checkRule(service("cbct")!, rohan, "2026-11-20", cal).ok).toBe(true);
    expect(checkRule(service("cbct")!, ishita, "2026-11-20", cal).ok).toBe(false);
    expect(checkRule(service("wisdom")!, ishita, "2026-11-20", cal).ok).toBe(false);
    expect(checkRule(service("wisdom")!, suresh, "2026-11-27", cal).ok).toBe(true);
    expect(checkRule(service("wisdom")!, null, "2026-11-27", cal).ok).toBe(null);
  });

  it("prices a change by the policy", () => {
    const suresh = cal.appts.get("DT-24078")!; // tomorrow 10:00, a check-up: within 24 h
    expect(changeTerms(suresh, cal)).toMatchObject({ allowed: true, fee: 300 });
    const scaling = cal.appts.get("DT-24063")!;
    expect(changeTerms(scaling, cal)).toMatchObject({ allowed: true, fee: 0 });
    expect(changeTerms({ ...scaling, changes: 2 }, cal)).toMatchObject({ allowed: false, callback: true });
  });
});
