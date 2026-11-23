/**
 * Paynora's payroll and income-tax engine, the TypeScript twin of
 * `backend/payroll_engine.py`. Same rules (read from data/product.json), same
 * rounding, same results: `engine.test.ts` holds it to every case in
 * data/tax_fixtures.json, which the Python engine writes. Change one, change both,
 * then run `uv run python payroll_app/data/build_data.py` and the tests.
 *
 * All amounts are whole rupees. Half-up to the rupee; total income and tax payable
 * to the nearest ₹10 (sections 288A / 288B). FY 2025-26 rules only.
 */
import product from "../../../data/product.json";

export type Regime = "new" | "old";
type RawSlab = (number | null)[];

export const FEBRUARY = 10;
export const FY_MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"];

/** a * num / den, half-up. Integer inputs keep the division exact at .5. */
const rnd = (a: number, num = 1, den = 1): number => Math.round((a * num) / den);
const ceilDiv = (a: number, num: number, den: number): number => Math.ceil((a * num) / den);
const round10 = (x: number): number => Math.floor((x + 5) / 10) * 10;

export interface Slab {
  lo: number;
  hi: number | null;
  rate: number;
}
interface RegimeRules {
  slabs: Slab[];
  standardDeduction: number;
  rebateLimit: number;
  rebateMax: number;
  marginalRelief: boolean;
}

const tax = product.tax;
const slabs = (raw: RawSlab[]): Slab[] => raw.map(([lo, hi, rate]) => ({ lo: lo as number, hi, rate: rate as number }));
const regimeRules = (r: (typeof tax.regimes)["new"]): RegimeRules => ({
  slabs: slabs(r.slabs as RawSlab[]),
  standardDeduction: r.standard_deduction,
  rebateLimit: r.rebate_87a.income_limit,
  rebateMax: r.rebate_87a.max,
  marginalRelief: r.rebate_87a.marginal_relief,
});
export const RULES = {
  new: regimeRules(tax.regimes.new),
  old: regimeRules(tax.regimes.old),
  cessPct: tax.cess_pct,
  limits: tax.limits as Record<string, number>,
  metroCities: tax.hra.metro_cities,
  hraMetroPct: tax.hra.metro_pct,
  hraNonMetroPct: tax.hra.non_metro_pct,
  hraRentMinusBasicPct: tax.hra.rent_minus_basic_pct,
  pfCeiling: tax.pf.wage_ceiling,
  pfPct: tax.pf.employee_pct,
  esiCeiling: tax.esi.gross_ceiling,
  esiEmployeeBp: Math.round(tax.esi.employee_pct * 100),
  esiEmployerBp: Math.round(tax.esi.employer_pct * 100),
  pt: Object.fromEntries(
    Object.entries(tax.professional_tax.states).map(([state, r]) => {
      const rule = r as { slabs: RawSlab[]; slabs_women?: RawSlab[]; february?: number };
      return [state, { slabs: slabs(rule.slabs), slabsWomen: rule.slabs_women ? slabs(rule.slabs_women) : null, february: rule.february ?? null }];
    }),
  ) as Record<string, { slabs: Slab[]; slabsWomen: Slab[] | null; february: number | null }>,
};

// ------------------------------------------------------------ structure

export interface Structure {
  basic: number;
  hra: number;
  lta: number;
  special: number;
  gross: number;
  employer_pf: number;
  employer_esi: number;
  esi_applicable: boolean;
  monthly_ctc: number;
}

export const isMetro = (city: string): boolean => RULES.metroCities.includes(city);

export function structure(ctc: number, city: string, ltaMonthly = 0): Structure {
  const monthly = rnd(ctc, 1, 12);
  const basic = rnd(monthly, 40, 100);
  const hra = rnd(basic, isMetro(city) ? RULES.hraMetroPct : RULES.hraNonMetroPct, 100);
  const erPf = rnd(Math.min(basic, RULES.pfCeiling), RULES.pfPct, 100);
  let gross = monthly - erPf;
  let erEsi = 0;
  let esi = false;
  const candidate = Math.floor(((monthly - erPf) * 10000) / (10000 + RULES.esiEmployerBp));
  if (candidate <= RULES.esiCeiling) {
    esi = true;
    erEsi = ceilDiv(candidate, RULES.esiEmployerBp, 10000);
    gross = monthly - erPf - erEsi;
  }
  const special = gross - basic - hra - ltaMonthly;
  return { basic, hra, lta: ltaMonthly, special, gross, employer_pf: erPf, employer_esi: erEsi, esi_applicable: esi, monthly_ctc: monthly };
}

export function professionalTax(state: string, gender: string, gross: number, monthIdx: number): number {
  const rule = RULES.pt[state];
  if (!rule) return 0;
  const list = gender === "F" && rule.slabsWomen ? rule.slabsWomen : rule.slabs;
  let amount = 0;
  for (const s of list) if (gross >= s.lo && (s.hi === null || gross <= s.hi)) amount = s.rate;
  if (amount === 200 && monthIdx === FEBRUARY && rule.february !== null) return rule.february;
  return amount;
}

export const employeePf = (earnedBasic: number): number => rnd(Math.min(earnedBasic, RULES.pfCeiling), RULES.pfPct, 100);
export const employeeEsi = (earnedGross: number, applicable: boolean): number =>
  applicable ? ceilDiv(earnedGross, RULES.esiEmployeeBp, 10000) : 0;

// ------------------------------------------------------------ income tax

export interface Declarations {
  rent_monthly: number;
  sec80c_other: number;
  sec80d_self: number;
  sec80d_parents: number;
  parents_senior: boolean;
  sec80ccd1b: number;
  home_loan_interest: number;
  lta_claim: number;
}
export const noDeclarations = (): Declarations => ({
  rent_monthly: 0,
  sec80c_other: 0,
  sec80d_self: 0,
  sec80d_parents: 0,
  parents_senior: false,
  sec80ccd1b: 0,
  home_loan_interest: 0,
  lta_claim: 0,
});

export interface AnnualSalary {
  gross: number;
  basic: number;
  hra: number;
  lta: number;
  employee_pf: number;
  professional_tax: number;
  months: number;
  metro: boolean;
}

export interface SlabLine {
  lo: number;
  hi: number | null;
  rate: number;
  taxable: number;
  tax: number;
}

export interface TaxBreakdown {
  regime: Regime;
  gross_salary: number;
  exempt_hra: number;
  exempt_lta: number;
  standard_deduction: number;
  professional_tax: number;
  income_from_salary: number;
  house_property: number;
  gross_total_income: number;
  ded_80c: number;
  ded_80ccd1b: number;
  ded_80d: number;
  total_deductions: number;
  taxable_income: number;
  slabs: SlabLine[];
  tax_on_income: number;
  rebate_87a: number;
  marginal_relief: number;
  tax_after_rebate: number;
  cess: number;
  total_tax: number;
}

export function hraExemption(sal: AnnualSalary, rentAnnual: number): number {
  if (rentAnnual <= 0 || sal.hra <= 0) return 0;
  const pct = sal.metro ? RULES.hraMetroPct : RULES.hraNonMetroPct;
  const rentLess = rentAnnual - rnd(sal.basic, RULES.hraRentMinusBasicPct, 100);
  return Math.max(0, Math.min(sal.hra, rentLess, rnd(sal.basic, pct, 100)));
}

export function slabTax(income: number, list: Slab[]): [number, SlabLine[]] {
  let total = 0;
  const lines: SlabLine[] = [];
  for (const s of list) {
    const top = s.hi === null ? income : Math.min(income, s.hi);
    const part = Math.max(0, top - s.lo);
    const t = rnd(part, s.rate, 100);
    lines.push({ lo: s.lo, hi: s.hi, rate: s.rate, taxable: part, tax: t });
    total += t;
  }
  return [total, lines];
}

export function computeTax(regime: Regime, sal: AnnualSalary, decl: Declarations): TaxBreakdown {
  const r = RULES[regime];
  const lim = RULES.limits;
  const old = regime === "old";
  const exemptHra = old ? hraExemption(sal, decl.rent_monthly * sal.months) : 0;
  const exemptLta = old ? Math.min(decl.lta_claim, sal.lta) : 0;
  const pt = old ? Math.min(sal.professional_tax, lim.professional_tax) : 0;
  const sd = Math.min(r.standardDeduction, sal.gross - exemptHra - exemptLta);
  const salaryIncome = Math.max(0, sal.gross - exemptHra - exemptLta - sd - pt);
  // `|| 0` keeps a JSON-identical 0 rather than -0 when there is no interest.
  const house = old ? -Math.min(decl.home_loan_interest, lim["24b"]) || 0 : 0;
  const gti = Math.max(0, salaryIncome + house);
  const d80c = old ? Math.min(lim["80C"], sal.employee_pf + decl.sec80c_other) : 0;
  const d80ccd = old ? Math.min(lim["80CCD1B"], decl.sec80ccd1b) : 0;
  const parentsCap = decl.parents_senior ? lim["80D_parents_senior"] : lim["80D_parents"];
  const d80d = old ? Math.min(decl.sec80d_self, lim["80D_self"]) + Math.min(decl.sec80d_parents, parentsCap) : 0;
  const totalDed = Math.min(gti, d80c + d80ccd + d80d);
  const taxable = round10(gti - totalDed);
  const [onIncome, lines] = slabTax(taxable, r.slabs);
  let rebate = 0;
  let relief = 0;
  if (taxable <= r.rebateLimit) rebate = Math.min(onIncome, r.rebateMax);
  else if (r.marginalRelief && onIncome > taxable - r.rebateLimit) relief = onIncome - (taxable - r.rebateLimit);
  const after = onIncome - rebate - relief;
  const cess = rnd(after, RULES.cessPct, 100);
  return {
    regime,
    gross_salary: sal.gross,
    exempt_hra: exemptHra,
    exempt_lta: exemptLta,
    standard_deduction: sd,
    professional_tax: pt,
    income_from_salary: salaryIncome,
    house_property: house,
    gross_total_income: gti,
    ded_80c: d80c,
    ded_80ccd1b: d80ccd,
    ded_80d: d80d,
    total_deductions: totalDed,
    taxable_income: taxable,
    slabs: lines,
    tax_on_income: onIncome,
    rebate_87a: rebate,
    marginal_relief: relief,
    tax_after_rebate: after,
    cess,
    total_tax: round10(after + cess),
  };
}

// ------------------------------------------------------------ payslip

export interface Ytd {
  gross: number;
  basic: number;
  hra: number;
  lta: number;
  employee_pf: number;
  professional_tax: number;
  tds: number;
  months: number;
}
export const emptyYtd = (): Ytd => ({ gross: 0, basic: 0, hra: 0, lta: 0, employee_pf: 0, professional_tax: 0, tds: 0, months: 0 });

export interface Payslip {
  month_idx: number;
  days: number;
  lop_days: number;
  paid_days: number;
  basic: number;
  hra: number;
  lta: number;
  special: number;
  gross: number;
  employee_pf: number;
  employee_esi: number;
  professional_tax: number;
  tds: number;
  reimbursements: number;
  total_deductions: number;
  net_pay: number;
  employer_pf: number;
  employer_esi: number;
  annual_tax: number;
}

export const ytdPlus = (y: Ytd, s: Payslip): Ytd => ({
  gross: y.gross + s.gross,
  basic: y.basic + s.basic,
  hra: y.hra + s.hra,
  lta: y.lta + s.lta,
  employee_pf: y.employee_pf + s.employee_pf,
  professional_tax: y.professional_tax + s.professional_tax,
  tds: y.tds + s.tds,
  months: y.months + 1,
});

export interface EmployeePay {
  ctc: number;
  city: string;
  state: string;
  gender: string;
  lta_monthly: number;
  regime: Regime;
  first_month_idx: number;
}

export function projectedAnnual(emp: EmployeePay, ytd: Ytd, cur: Payslip | null, monthIdx: number): AnnualSalary {
  const st = structure(emp.ctc, emp.city, emp.lta_monthly);
  let { gross, basic, hra, lta, employee_pf: pf, professional_tax: pt, months } = ytd;
  let start = monthIdx;
  if (cur) {
    gross += cur.gross;
    basic += cur.basic;
    hra += cur.hra;
    lta += cur.lta;
    pf += cur.employee_pf;
    pt += cur.professional_tax;
    months += 1;
    start = monthIdx + 1;
  }
  for (let m = Math.max(start, emp.first_month_idx); m < 12; m++) {
    gross += st.gross;
    basic += st.basic;
    hra += st.hra;
    lta += st.lta;
    pf += employeePf(st.basic);
    pt += professionalTax(emp.state, emp.gender, st.gross, m);
    months += 1;
  }
  return { gross, basic, hra, lta, employee_pf: pf, professional_tax: pt, months, metro: isMetro(emp.city) };
}

export function payslip(
  emp: EmployeePay,
  monthIdx: number,
  days: number,
  lopDays: number,
  ytd: Ytd,
  decl: Declarations,
  reimbursements = 0,
  regime?: Regime,
): Payslip {
  const st = structure(emp.ctc, emp.city, emp.lta_monthly);
  const paid = days - lopDays;
  const earned = (x: number) => rnd(x, paid, days);
  const basic = earned(st.basic);
  const hra = earned(st.hra);
  const lta = earned(st.lta);
  const special = earned(st.special);
  const gross = basic + hra + lta + special;
  const pf = employeePf(basic);
  const esi = employeeEsi(gross, st.esi_applicable);
  const pt = professionalTax(emp.state, emp.gender, gross, monthIdx);
  const slip: Payslip = {
    month_idx: monthIdx,
    days,
    lop_days: lopDays,
    paid_days: paid,
    basic,
    hra,
    lta,
    special,
    gross,
    employee_pf: pf,
    employee_esi: esi,
    professional_tax: pt,
    tds: 0,
    reimbursements,
    total_deductions: 0,
    net_pay: 0,
    employer_pf: employeePf(basic),
    employer_esi: st.esi_applicable ? ceilDiv(gross, RULES.esiEmployerBp, 10000) : 0,
    annual_tax: 0,
  };
  const annual = projectedAnnual(emp, ytd, slip, monthIdx);
  const yearTax = computeTax(regime ?? emp.regime, annual, decl).total_tax;
  slip.tds = Math.max(0, rnd(yearTax - ytd.tds, 1, 12 - monthIdx));
  slip.annual_tax = yearTax;
  slip.total_deductions = pf + esi + pt + slip.tds;
  slip.net_pay = gross - slip.total_deductions + reimbursements;
  return slip;
}

export interface RegimeComparison {
  annual_salary: AnnualSalary;
  new: TaxBreakdown;
  old: TaxBreakdown;
  better: Regime;
  saving: number;
}

export function regimeComparison(emp: EmployeePay, ytd: Ytd, monthIdx: number, decl: Declarations): RegimeComparison {
  const annual = projectedAnnual(emp, ytd, null, monthIdx);
  const n = computeTax("new", annual, decl);
  const o = computeTax("old", annual, decl);
  return { annual_salary: annual, new: n, old: o, better: n.total_tax <= o.total_tax ? "new" : "old", saving: Math.abs(n.total_tax - o.total_tax) };
}
