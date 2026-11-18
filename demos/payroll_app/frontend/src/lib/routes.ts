/**
 * What each app path is, for the tab title and `screen.viewed`
 * ({path, title, employee_id?, tab?}).
 */
import { COMPANY } from "./data";
import { monthLabel } from "./format";

const name = (id: string) => COMPANY.employees.find((e) => e.id === id)?.name ?? id;
const RUN_LABEL = (id: string) => COMPANY.payroll_runs.find((r) => r.id === id)?.label ?? id;

export interface Screen {
  path: string;
  title: string;
  employee_id?: string;
  tab?: string;
}

export const PAGES = {
  Dashboard: "/",
  Employees: "/employees",
  Payroll: "/payroll",
  Payslips: "/payslips",
  Leave: "/leave",
  Reimbursements: "/reimbursements",
  Tax: "/tax",
  Settings: "/settings",
  Help: "/help",
  Setup: "/welcome",
} as const;
export type PageName = keyof typeof PAGES;

export function screenOf(pathname: string, search = ""): Screen {
  const q = new URLSearchParams(search);
  const tab = q.get("tab") ?? undefined;
  const p = pathname.replace(/\/+$/, "") || "/";
  const parts = p.split("/").filter(Boolean);
  const s = (title: string, extra: Partial<Screen> = {}): Screen => ({ path: p + (search && search !== "?" ? search : ""), title, ...(tab ? { tab } : {}), ...extra });
  switch (parts[0]) {
    case undefined:
      return s("Dashboard");
    case "welcome":
      return s("Setup");
    case "employees":
      if (parts[1] === "new") return s("Add employee");
      if (parts[1]) return s(name(parts[1]), { employee_id: parts[1] });
      return s("Employees");
    case "payroll":
      return parts[1] ? s(`${RUN_LABEL(parts[1])} payroll run`) : s("Payroll runs");
    case "payslips":
      if (parts[1] && parts[2]) {
        const against = q.get("against");
        return s(`${name(parts[1])}, payslip for ${monthLabel(parts[2])}${against ? ` against ${monthLabel(against)}` : ""}`, { employee_id: parts[1] });
      }
      return s("Payslips");
    case "leave":
      return s("Leave");
    case "reimbursements":
      return s("Reimbursements");
    case "tax":
      if (parts[1] === "regime" && parts[2]) return s(`${name(parts[2])}, regime comparison`, { employee_id: parts[2] });
      return s("Tax");
    case "settings":
      return s("Settings");
    case "help":
      return s("Help");
    case "me":
      return { path: p, title: `Employee view: ${name(parts[1] ?? "")}`, employee_id: parts[1], tab: parts[2] ?? "payslips" };
    default:
      return s("Not found");
  }
}

/** The app paths a move may open, as patterns. */
export const ROUTE_PATTERNS = [
  /^\/$/,
  /^\/welcome$/,
  /^\/employees(\/new|\/BB-\d{4})?$/,
  /^\/payroll(\/PR-\d{4}-\d{2})?$/,
  /^\/payslips(\/BB-\d{4}\/\d{4}-\d{2})?$/,
  /^\/leave$/,
  /^\/reimbursements$/,
  /^\/tax(\/regime\/BB-\d{4})?$/,
  /^\/settings$/,
  /^\/help$/,
  /^\/me\/BB-\d{4}\/(payslips|tax|declarations|leave)$/,
];
