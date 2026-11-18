/**
 * The router, for code outside React: performers navigate with the app's own
 * router (a history push, never a page load) and read where the app is.
 */
type Navigate = (to: string, opts?: { replace?: boolean }) => void;
let navigate: Navigate | null = null;
let where: () => string = () => window.location.pathname;

export function bindRouter(fn: Navigate, current: () => string) {
  navigate = fn;
  where = current;
  return () => {
    if (navigate === fn) navigate = null;
  };
}

/** Go to an app path (without the base): "/leave?tab=requests". */
export function go(to: string, replace = false) {
  if (navigate) navigate(to, { replace });
  else window.history.pushState({}, "", `${import.meta.env.BASE_URL.replace(/\/$/, "")}${to}`);
}

/** The app path in front, without the base, with its query. */
export const currentPath = (): string => where();
