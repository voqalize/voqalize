/**
 * The router, for code outside React (Stage performers, the debug console):
 * the app shell binds `navigate` and the current path once.
 */
export type Page = "home" | "book" | "my-appointments";

export const PATH: Record<Page, string> = { home: "/", book: "/book", "my-appointments": "/my-appointments" };

let go: ((to: string) => void) | null = null;
let where: () => string = () => "/";

export function bindRouter(navigate: (to: string) => void, path: () => string) {
  go = navigate;
  where = path;
  return () => {
    go = null;
  };
}

/** The route the app is on, without the base: "/", "/book"… */
export const currentPath = () => where();

export function pageOf(path: string): Page {
  if (path.startsWith("/book")) return "book";
  if (path.startsWith("/my-appointments")) return "my-appointments";
  return "home";
}

export const currentPage = () => pageOf(currentPath());

/** Who moved the page last: a performer sets "agent" around its own navigate. */
let navBy: "visitor" | "agent" = "visitor";
export const navigatedBy = () => navBy;

export function navigate(to: string, by: "visitor" | "agent" = "visitor") {
  navBy = by;
  go?.(to);
  // Back to the visitor once this route change has been reported.
  setTimeout(() => {
    navBy = "visitor";
  }, 300);
}
