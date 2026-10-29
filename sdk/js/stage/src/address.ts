/**
 * What the page tells the agent about where it is: its origin and path, and
 * nothing else.
 *
 * The query and the fragment are where a page keeps its state and its
 * secrets (a sign-in token, an order id, an email), and the title is often
 * the person's own data ("Order #1234 — Jane"), so neither leaves the page
 * by default. The userinfo of a URL is dropped with them, since the origin
 * never carries it. A path is cut to `PATH_MAX` characters, so an address
 * that stuffs a blob into its path cannot carry all of it.
 *
 * A page that needs the agent to know more says so itself, with
 * `send({ runtime, contract, url, title })` on what `attachStage` or
 * `stagePage` returns.
 */

/** The longest path, in characters, the agent is told. */
export const PATH_MAX = 160;

/** `path`, cut to `PATH_MAX` characters. */
export function clipPath(path: string): string {
  return path.length > PATH_MAX ? `${path.slice(0, PATH_MAX - 1)}…` : path;
}

/** `href` as the agent may hear it: origin and path, no query, no fragment.
 *  Something that is not a URL comes back empty. */
export function pageAddress(href: string): string {
  let u: URL;
  try {
    u = new URL(href);
  } catch {
    return "";
  }
  // `origin` is "null" for a URL with an opaque origin (data:, file:, about:).
  const origin = u.origin === "null" ? `${u.protocol}` : u.origin;
  return `${origin}${clipPath(u.pathname)}`;
}
