/**
 * Which page a URL names, as the brain names pages: host (bare uahurtado.cl is
 * www), path without its trailing slash, and query. Shared by the adapter (the
 * page in front) and the holder's narration (the page the visitor's UAH tab
 * shows), so both agree on "another page".
 */

const hostKey = (h: string) => (h.toLowerCase() === "uahurtado.cl" ? "www.uahurtado.cl" : h.toLowerCase());
const pathKey = (p: string) => (p || "/").replace(/\/+$/, "").toLowerCase() || "/";

/** Whether `a` and `b` are the same page: same host, path and query. */
export function samePageAs(a: URL, b: URL): boolean {
  return hostKey(a.host) === hostKey(b.host) && pathKey(a.pathname) === pathKey(b.pathname) && a.search === b.search;
}

/** Whether `url` names another page than `shown` (`null`: no UAH tab yet, so
 *  it does). An address that is not a URL names no page. */
export function elsewhereThan(url: string, shown: string | null): boolean {
  try {
    if (!shown) return true;
    const base = new URL(shown);
    return !samePageAs(new URL(url, base), base);
  } catch {
    return false;
  }
}
