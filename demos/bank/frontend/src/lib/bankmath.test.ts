/**
 * The page's maths, pinned to the numbers the brain computes (backend/bankmath.py;
 * the same figures are asserted in demos/tests/test_bank_e2e.py). If one side
 * changes, both tests must change together, or the agent and the screen disagree.
 */
import { describe, expect, it } from "vitest";
import { customer, products } from "../data/bank";
import { cardEmi, customerProfile, emi, fdQuote, loanEligibility, rankCards } from "./bankmath";

describe("bankmath agrees with the brain", () => {
  it("the customer's spend profile", () => {
    expect(customerProfile()).toEqual({ dining: 13700, online: 44000, groceries: 7300, travel: 22000, fuel: 5400, utilities: 3500, other: 100 });
  });
  it("ranks the cards for her spend", () => {
    expect(rankCards(customerProfile()).map((v) => [v.card_id, v.net_yearly])).toEqual([
      ["prism", 49048],
      ["voyage", 38776],
      ["daily", 27520],
      ["spark", 13479],
      ["fuelone", 9114],
    ]);
  });
  it("signed in, ranks the cards her income qualifies for first", () => {
    const r = rankCards(customerProfile(), customer.profile.monthly_income);
    expect(r.map((v) => [v.card_id, v.net_yearly, v.below_income])).toEqual([
      ["voyage", 38776, false],
      ["daily", 27520, false],
      ["spark", 13479, false],
      ["fuelone", 9114, false],
      ["prism", 49048, true],
    ]);
  });
  it("ranks the cards for a typed profile", () => {
    const r = rankCards({ dining: 8000, online: 6000, groceries: 0, travel: 0, fuel: 2000, utilities: 0, other: 0 });
    expect(r.map((v) => [v.card_id, v.net_yearly, v.yearly_rewards, v.fuel_saving_yearly, v.fee_waived])).toEqual([
      ["daily", 7891, 8400, 240, false],
      ["spark", 4440, 4200, 240, true],
      ["fuelone", 2040, 1800, 240, true],
      ["voyage", -239, 2520, 240, false],
      ["prism", -4159, 5600, 240, false],
    ]);
  });
  it("card EMI", () => {
    expect(cardEmi(64990, 6)).toEqual({ months: 6, rate: 14, emi: 11278, total_interest: 2678, processing_fee: 650, gst_on_fee: 117, total_cost: 3445 });
    expect(cardEmi(4999, 3).emi).toBe(1703);
  });
  it("loan eligibility and EMI", () => {
    const home = products.loans.find((l) => l.id === "home")!;
    const e = loanEligibility(home, { monthly_income: 120000, existing_emis: 15000 });
    expect([e.max_emi, e.max_amount, e.tenure_months]).toEqual([51000, 5720000, 240]);
    expect(Math.round(emi(5000000, 8.85, 240))).toBe(44505);
    const gold = products.loans.find((l) => l.id === "gold")!;
    expect(loanEligibility(gold, { gold_grams: 50 }).max_amount).toBe(270000);
  });
  it("FD quotes", () => {
    expect(fdQuote(100000, 12, "cumulative")).toMatchObject({ rate: 7.1, maturity: 107291 });
    expect(fdQuote(100000, 24, "monthly")).toMatchObject({ rate: 7.4, payout_each: 617, interest: 14800 });
  });
});
