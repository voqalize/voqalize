/**
 * The amortisation summary the loan pages show beside the EMI: how the first
 * year's instalments split into interest and principal. Display only; the EMI
 * itself is `emi()` from bankmath, rounded to the rupee as everywhere else.
 */
import { emi } from "./bankmath";

export interface Amortised {
  emi: number;
  r: number;
  growth: number;
  total_payable: number;
  total_interest: number;
  months: number;
  first_year: { interest: number; principal: number; balance_after: number };
}

export function amortise(principal: number, ratePa: number, months: number): Amortised {
  const m = Math.round(emi(principal, ratePa, months));
  const r = ratePa / 12 / 100;
  let balance = principal;
  let interest = 0;
  let paid = 0;
  for (let i = 0; i < Math.min(12, months); i++) {
    const int = balance * r;
    const prin = Math.min(balance, m - int);
    interest += int;
    paid += prin;
    balance -= prin;
  }
  return {
    emi: m,
    r,
    growth: Math.pow(1 + r, months),
    total_payable: m * months,
    total_interest: m * months - principal,
    months,
    first_year: { interest: Math.round(interest), principal: Math.round(paid), balance_after: Math.max(0, Math.round(balance)) },
  };
}
