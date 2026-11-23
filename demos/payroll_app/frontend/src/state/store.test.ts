import { beforeEach, describe, expect, it } from "vitest";
import { COMPANY } from "../lib/data";
import { FEBRUARY, payslip, regimeComparison } from "../lib/engine";
import { declOf, febSlip, payOf, parseCsv, testPayroll, totalsOf, validateImport } from "../lib/payroll";
import importCsv from "../../../data/employees_import.csv?raw";
import { eventLog } from "../stage/runtime";
import * as S from "./store";

const draft = COMPANY.payroll_runs.find((r) => r.id === "PR-2026-02")!;
const KEYS = ["employees", "gross", "employee_pf", "employer_pf", "employee_esi", "employer_esi", "professional_tax", "tds", "reimbursements", "net_pay", "lop_days", "employer_cost"] as const;
const pick = (r: Record<string, unknown>) => Object.fromEntries(KEYS.map((k) => [k, r[k]]));
const lastEvent = () => eventLog().filter((e) => e.kind === "event").at(-1)!;

beforeEach(() => S.resetSession());

describe("the February draft", () => {
  it("recomputed by the store's rule equals company.json's PR-2026-02", () => {
    const s = S.useTk.getState();
    for (const e of s.employees) {
      const mine = febSlip(e, s.febLop[e.id] ?? 0, declOf(e.id, s.declarations), s.claims.filter((c) => c.employee_id === e.id && c.payroll_month === "2026-02" && c.status === "approved").reduce((n, c) => n + c.amount, 0));
      const theirs = s.payslips[e.id]!.find((x) => x.month === "2026-02")!;
      expect({ ...mine, month: theirs.month }).toMatchObject({ net_pay: theirs.net_pay, tds: theirs.tds, gross: theirs.gross });
    }
    const slips = s.employees.map((e) =>
      febSlip(e, s.febLop[e.id] ?? 0, declOf(e.id, s.declarations), s.claims.filter((c) => c.employee_id === e.id && c.payroll_month === "2026-02" && c.status === "approved").reduce((n, c) => n + c.amount, 0)),
    );
    expect(pick(totalsOf(slips) as unknown as Record<string, unknown>)).toEqual(pick(draft as unknown as Record<string, unknown>));
    expect([draft.gross, draft.net_pay, draft.tds]).toEqual([6066038, 5385880, 573249]);
  });

  it("a change and its reverse bring the store's draft back to company.json's totals", () => {
    expect(S.switchRegime("BB-1001", "old").ok).toBe(true);
    expect(S.draftRun().tds).not.toBe(draft.tds);
    expect(S.switchRegime("BB-1001", "new").ok).toBe(true);
    expect(pick(S.draftRun() as unknown as Record<string, unknown>)).toEqual(pick(draft as unknown as Record<string, unknown>));
  });
});

describe("approving leave", () => {
  it("LV-2412 (Asha Chavan, 2 CL with 1 CL left) makes 1 LOP day and recomputes her February payslip", () => {
    const asha = S.employee("BB-1046")!;
    expect(asha.name).toBe("Asha Chavan");
    expect(asha.leave_balance.CL).toBe(1);
    const before = S.febSlipOf("BB-1046")!;
    const r = S.approveLeave("LV-2412");
    expect(r.ok).toBe(true);
    const after = S.febSlipOf("BB-1046")!;
    const want = payslip(payOf(asha), FEBRUARY, 28, 1, asha.ytd_to_jan, declOf(asha.id, COMPANY.declarations), 0, asha.tax_regime);
    expect(after.lop_days).toBe(1);
    expect(after.net_pay).toBe(want.net_pay);
    expect(after.gross).toBe(want.gross);
    expect(after.net_pay).toBeLessThan(before.net_pay);
    expect(S.employee("BB-1046")!.leave_balance.CL).toBe(0);
    expect(S.draftRun().net_pay).toBe(draft.net_pay - (before.net_pay - after.net_pay));
    expect(S.draftRun().lop_days).toBe(1);
    expect(lastEvent()).toMatchObject({ name: "leave.decided", by: "visitor", data: { request_id: "LV-2412", decision: "approve", lop_days: 1 } });
  });

  it("a March leave changes no February number; reject is status only", () => {
    expect(S.approveLeave("LV-2411").ok).toBe(true);
    expect(S.draftRun().net_pay).toBe(draft.net_pay);
    expect(S.rejectLeave("LV-2409").ok).toBe(true);
    expect(S.draftRun().net_pay).toBe(draft.net_pay);
    expect(S.approveLeave("LV-2409").ok).toBe(false);
  });
});

describe("claims", () => {
  it("fixing RB-3108 sets ₹4,580 and adds it to Imran's February reimbursements", () => {
    const before = S.febSlipOf("BB-1032")!;
    expect(S.employee("BB-1032")!.name).toBe("Imran Qureshi");
    expect(S.fixClaim("RB-3108", 4850).ok).toBe(false);
    expect(S.fixClaim("RB-3108", 4580).ok).toBe(true);
    const c = S.useTk.getState().claims.find((x) => x.id === "RB-3108")!;
    expect(c).toMatchObject({ amount: 4580, status: "approved" });
    const after = S.febSlipOf("BB-1032")!;
    expect(after.reimbursements).toBe(before.reimbursements + 4580);
    expect(after.net_pay).toBe(before.net_pay + 4580);
    expect(after.tds).toBe(before.tds);
    expect(S.draftRun().reimbursements).toBe(draft.reimbursements + 4580);
    expect(lastEvent()).toMatchObject({ name: "claim.changed", data: { claim_id: "RB-3108", status: "approved", amount: 4580 } });
  });

  it("a claim that needs a fix cannot be approved as it stands", () => {
    expect(S.decideClaim("RB-3108", "approve").ok).toBe(false);
    expect(S.decideClaim("RB-3109", "approve").ok).toBe(true);
    expect(S.febSlipOf("BB-1051")!.reimbursements).toBe(11240);
  });
});

describe("regimes", () => {
  it("Kavitha: new ₹6,56,260 vs old ₹6,27,090, saving ₹29,170", () => {
    const k = S.employee("BB-1007")!;
    const cmp = regimeComparison(payOf(k), k.ytd_to_jan, FEBRUARY, declOf(k.id, COMPANY.declarations));
    expect(cmp.new.total_tax).toBe(656260);
    expect(cmp.old.total_tax).toBe(627090);
    expect(cmp.better).toBe("old");
    expect(cmp.saving).toBe(29170);
  });

  it("switching BB-1007 to old recomputes TDS for the months left", () => {
    const k = S.employee("BB-1007")!;
    const before = S.febSlipOf("BB-1007")!;
    expect(S.switchRegime("BB-1007", "old").ok).toBe(true);
    const after = S.febSlipOf("BB-1007")!;
    expect(after.annual_tax).toBe(627090);
    expect(after.tds).toBe(Math.round((627090 - k.ytd_to_jan.tds) / 2));
    expect(after.tds).toBeLessThan(before.tds);
    expect(S.employee("BB-1007")!.tax_regime).toBe("old");
    expect(S.draftRun().tds).toBe(draft.tds - (before.tds - after.tds));
    expect(lastEvent()).toMatchObject({ name: "regime.switched", data: { employee_id: "BB-1007", regime: "old" } });
  });
});

describe("a new joiner", () => {
  it("joining 2026-02-16 gives BB-1057 a prorated payslip with 15 LOP days", () => {
    const form = {
      name: "Nandini Iyer",
      email: "nandini.iyer@banyanbay.example",
      gender: "F",
      department: "Marketing",
      title: "Brand Manager",
      grade: "G4",
      location: "Bengaluru",
      joined: "2026-02-16",
      annual_ctc: "720000",
      tax_regime: "new",
      manager_id: "BB-1022",
    } as const;
    for (const [k, v] of Object.entries(form)) S.setNewField(k as never, v);
    const r = S.saveEmployee();
    expect(r.ok).toBe(true);
    const e = S.employee("BB-1057")!;
    expect(e.name).toBe("Nandini Iyer");
    const slip = S.febSlipOf("BB-1057")!;
    expect(slip.lop_days).toBe(15);
    expect(slip.paid_days).toBe(13);
    expect(slip.basic).toBe(Math.round((e.structure.basic * 13) / 28));
    expect(S.draftRun().employees).toBe(57);
    expect(S.draftRun().gross).toBe(draft.gross + slip.gross);
    expect(lastEvent()).toMatchObject({ name: "employee.added", data: { employee_id: "BB-1057", annual_ctc: 720000 } });
    expect((lastEvent().data as Record<string, unknown>).email).toBeUndefined();
  });
});

describe("setup's test payroll", () => {
  it("over employees_import.csv equals the February draft", () => {
    const { rows } = parseCsv(importCsv);
    const v = validateImport(rows);
    expect(rows.length).toBe(56);
    expect(v.valid).toBe(56);
    expect(v.issues).toEqual([]);
    const { totals } = testPayroll(rows);
    expect(pick(totals as unknown as Record<string, unknown>)).toEqual(pick(draft as unknown as Record<string, unknown>));
  });

  it("validation names bad PANs, duplicates and unknown managers", () => {
    const { rows } = parseCsv(importCsv);
    const bad = [...rows.slice(0, 3), { ...rows[3]!, pan: "ABC123" }, { ...rows[4]!, employee_id: rows[0]!.employee_id }, { ...rows[5]!, manager_id: "BB-9999" }];
    const v = validateImport(bad);
    expect(v.valid).toBe(3);
    expect(v.issues.map((i) => i.problem).join("|")).toMatch(/PAN ABC123.*appears twice.*BB-9999/);
  });

  it("the store's import, test run and finish", () => {
    expect(S.runTestPayroll().ok).toBe(false);
    S.importEmployees();
    const r = S.runTestPayroll();
    expect(r.ok && r.detail).toContain("₹60,66,038");
    expect(S.useTk.getState().setup.test!.totals.net_pay).toBe(5385880);
    expect(S.finishSetup().ok).toBe(true);
  });
});

describe("Ravi's January payslip against December", () => {
  it("Dec net ₹1,26,374 → Jan ₹1,11,959", () => {
    expect(S.slipOf("BB-1030", "2025-12")!.net_pay).toBe(126374);
    expect(S.slipOf("BB-1030", "2026-01")!.net_pay).toBe(111959);
  });
});

// Keep the regime comparison against company.json's precomputed numbers for every employee.
describe("regime comparison for everyone", () => {
  it("matches employees[].regime_comparison", () => {
    for (const e of COMPANY.employees) {
      const cmp = regimeComparison(payOf(e), e.ytd_to_jan, FEBRUARY, declOf(e.id, COMPANY.declarations));
      expect([e.id, cmp.new.total_tax, cmp.old.total_tax]).toEqual([e.id, e.regime_comparison.new_total, e.regime_comparison.old_total]);
    }
  });
});

describe("the hand-off request (A4)", () => {
  it("a draft carries its kind, opens the drawer, and sends without leaving the screen", () => {
    expect(S.useTk.getState().handoffOpen).toBe(false);
    const r = S.draftTicket({ kind: "feature", subject: "Bulk regime switch", summary: "Asked: switch ten people at once.", employee_id: null });
    expect(r.ok).toBe(true);
    expect(r.ok && r.detail).toContain("feature request");
    expect(S.useTk.getState()).toMatchObject({ handoffOpen: true, ticketDraft: { kind: "feature", subject: "Bulk regime switch" } });
    const sent = S.submitTicket();
    expect(sent.ok && sent.detail).toMatch(/^feature request TK-\d+ sent/);
    const st = S.useTk.getState();
    expect(st.handoffOpen).toBe(false);
    expect(st.ticketDraft).toBeNull();
    expect(st.tickets[0]).toMatchObject({ kind: "feature", subject: "Bulk regime switch", status: "open" });
    expect(lastEvent()).toMatchObject({ name: "ticket.created" });
  });

  it("a draft with no kind is a support request; closing keeps the draft, discarding drops it", () => {
    S.draftTicket({ subject: "Ravi's TDS", summary: "Needed: a check.", employee_id: "BB-1030" });
    expect(S.useTk.getState().ticketDraft?.kind).toBe("support");
    S.closeHandoff();
    expect(S.useTk.getState()).toMatchObject({ handoffOpen: false, ticketDraft: { subject: "Ravi's TDS" } });
    S.openHandoff("feature");
    expect(S.useTk.getState().ticketDraft?.kind).toBe("support");
    S.discardTicketDraft();
    expect(S.useTk.getState()).toMatchObject({ handoffOpen: false, ticketDraft: null });
    S.openHandoff("feature");
    expect(S.useTk.getState().ticketDraft).toMatchObject({ kind: "feature", subject: "" });
  });
});

describe("the claim drawer", () => {
  it("opens and closes from the store, so a move opens the same drawer a click does", () => {
    S.openClaimDrawer("RB-3109");
    expect(S.useTk.getState().openClaim).toBe("RB-3109");
    S.closeClaimDrawer();
    expect(S.useTk.getState().openClaim).toBeNull();
  });
});
