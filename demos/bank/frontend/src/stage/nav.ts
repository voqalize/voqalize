/**
 * Screens ↔ paths (CONTRACT.md "Routes"), the router seam performers use to
 * navigate, and a small wait for React to put something on the page.
 */
export type Screen =
  | "home" | "login" | "dashboard" | "account" | "transactions" | "insights" | "cards_hub" | "debit_card"
  | "credit_card" | "payments" | "bills" | "deposits" | "statements" | "offers" | "open_account" | "cards"
  | "card_detail" | "cards_compare" | "cards_apply" | "cards_emi" | "loans" | "loan" | "loan_apply";

export function screenPath(screen: Screen, id?: string | null): string {
  switch (screen) {
    case "home": return "/";
    case "login": return "/login";
    case "dashboard": return "/app";
    case "account": return `/app/accounts/${id ?? "sb"}`;
    case "transactions": return "/app/transactions";
    case "insights": return "/app/insights";
    case "cards_hub": return "/app/cards";
    case "debit_card": return "/app/cards/debit";
    case "credit_card": return "/app/cards/credit";
    case "payments": return "/app/payments";
    case "bills": return "/app/bills";
    case "deposits": return "/app/deposits";
    case "statements": return "/app/statements";
    case "offers": return "/app/offers";
    case "open_account": return "/open-account";
    case "cards": return "/cards";
    case "card_detail": return `/cards/${id ?? "spark"}`;
    case "cards_compare": return "/cards/compare";
    case "cards_apply": return id ? `/cards/apply?card=${id}` : "/cards/apply";
    case "cards_emi": return id ? `/cards/emi?txn=${id}` : "/cards/emi";
    case "loans": return "/loans";
    case "loan": return `/loans/${id ?? "home"}`;
    case "loan_apply": return id ? `/loans/apply?type=${id}` : "/loans/apply";
  }
}

/** The screen a path shows (the inverse of screenPath, ignoring ids). */
export function screenOf(path: string): Screen {
  const p = path.replace(/\/+$/, "") || "/";
  if (p === "/") return "home";
  if (p === "/login") return "login";
  if (p === "/app") return "dashboard";
  if (p.startsWith("/app/accounts")) return "account";
  if (p.startsWith("/app/transactions")) return "transactions";
  if (p.startsWith("/app/insights")) return "insights";
  if (p === "/app/cards") return "cards_hub";
  if (p.startsWith("/app/cards/debit")) return "debit_card";
  if (p.startsWith("/app/cards/credit")) return "credit_card";
  if (p.startsWith("/app/payments")) return "payments";
  if (p.startsWith("/app/bills")) return "bills";
  if (p.startsWith("/app/deposits")) return "deposits";
  if (p.startsWith("/app/statements")) return "statements";
  if (p.startsWith("/app/offers")) return "offers";
  if (p.startsWith("/open-account")) return "open_account";
  if (p === "/cards") return "cards";
  if (p.startsWith("/cards/compare")) return "cards_compare";
  if (p.startsWith("/cards/apply")) return "cards_apply";
  if (p.startsWith("/cards/emi")) return "cards_emi";
  if (p.startsWith("/cards/")) return "card_detail";
  if (p === "/loans") return "loans";
  if (p.startsWith("/loans/apply")) return "loan_apply";
  if (p.startsWith("/loans/")) return "loan";
  return "home";
}

type Go = (to: string, replace?: boolean) => void;
let go: Go | null = null;
let where: () => string = () => "/";

/** The app shell binds the router once. */
export function bindRouter(navigate: Go, path: () => string) {
  go = navigate;
  where = path;
  return () => {
    go = null;
  };
}

export const currentPath = () => where();

export function navigateTo(to: string, replace = false) {
  go?.(to, replace);
}

/** Wait for React to put `find()` on the page (a screen that just opened). */
export async function appear<T extends Element>(find: () => T | null, ms = 1500): Promise<T | null> {
  const end = Date.now() + ms;
  for (;;) {
    const el = find();
    if (el || Date.now() > end) return el;
    await new Promise((r) => setTimeout(r, 30));
  }
}

/** The element marked `data-stage-thing="<name>"`. */
export const thing = (name: string) => document.querySelector<HTMLElement>(`[data-stage-thing="${CSS.escape(name)}"]`);
