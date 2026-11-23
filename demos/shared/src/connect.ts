/**
 * Where a demo page sends `sessions.connect`: the environment's signalling
 * host, `signal.<env>.voqalize.com`, rather than the control plane.
 *
 * The environment follows the page's host, because one demo build is laid
 * under both `voqalize.com` and `dev.voqalize.com`. Any other host (a local
 * stack, a Vite dev server, a preview) keeps the same-origin `/api/v1`, which
 * that host proxies, as every demo did before.
 */
export function connectApiBase(host: string = location.hostname): string {
  if (host === "voqalize.com" || host === "www.voqalize.com") return "https://signal.prod.voqalize.com/api/v1";
  if (host === "dev.voqalize.com") return "https://signal.dev.voqalize.com/api/v1";
  return "/api/v1";
}
