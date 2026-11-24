import { describe, expect, it } from "vitest";
import fixtures from "../../../data/tax_fixtures.json";
import company from "../../../data/company.json";
import * as E from "./engine";

// data/tax_fixtures.json is written by data/build_data.py from the Python engine.
// Every case must come out identical here, so the screen and the brain agree.
type Case = Record<string, any>;
const cases = (fixtures as { cases: Case[] }).cases;

describe("engine.ts matches payroll_engine.py", () => {
  it.each(cases.map((c, i) => [i, c.kind, c] as const))("case %i (%s)", (_i, kind, c) => {
    let got: unknown;
    if (kind === "tax") got = E.computeTax(c.regime, c.salary, c.decl);
    else if (kind === "structure") got = E.structure(c.pay.ctc, c.pay.city, c.pay.lta_monthly);
    else if (kind === "payslip") got = E.payslip(c.pay, c.month_idx, c.days, c.lop, c.ytd, c.decl, c.reimbursements);
    else got = E.regimeComparison(c.pay, c.ytd, c.month_idx, c.decl);
    expect(got).toEqual(c.out);
  });

  it("reproduces Ravi's January payslip from company.json", () => {
    const ravi = company.employees.find((e) => e.name === "Ravi Kumar")!;
    const jan = (company.payslips as Record<string, Case[]>)[ravi.id].find((s) => s.month === "2026-01")!;
    expect(jan.lop_days).toBe(2);
    expect(jan.tds).toBe(company.stories.ravi_net_drop.tds_jan);
  });
});
