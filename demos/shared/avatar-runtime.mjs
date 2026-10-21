/**
 * Load an unreleased avatar runtime without releasing `@voqalize/avatar`.
 *
 * The shim names the runtime it loads in one module of its own,
 * `@voqalize/avatar/dist/pin.js`. With `AVATAR_RUNTIME` set, this Vite plugin
 * serves that module with the URL swapped, and keeps the shim's `PROTOCOL`, so
 * the runtime still refuses a shim it does not speak. Unset — every prod build —
 * it returns nothing and the build is exactly what npm gives a customer.
 *
 *   AVATAR_RUNTIME=https://avatar.local.voqalize.com/runtime/current.js   # the newest local build
 *   AVATAR_RUNTIME=https://avatar.dev.voqalize.com/runtime/current.js     # the last dev upload
 *
 * `current.js` is the newest runtime each host has, not a release. A demo you
 * copy from here needs none of this: leave `AVATAR_RUNTIME` unset.
 *
 * Only those hosts are accepted. A runtime on `avatar.voqalize.com` reaches a
 * page through a release of `@voqalize/avatar`, never through this override:
 * from 2026-10-16 to the 0.6.0 release the prod demos trigger named one here by
 * hand, and the prod pages kept a runtime no release pinned, out of sight of
 * every repository. `unreleasedRuntime()` fails that build instead.
 *
 * The shim is kept out of dependency pre-bundling while overridden, because
 * the pre-bundler reads `pin.js` without running plugins.
 */
import { readFileSync } from "node:fs";

const PIN = /[\\/]@voqalize[\\/]avatar[\\/]dist[\\/]pin\.js$/;
const URL_LINE = /export const RUNTIME_URL = "[^"]*";/;
const UNRELEASED_HOSTS = ["avatar.dev.voqalize.com", "avatar.local.voqalize.com"];

/** `url`, if it is a runtime on a host of unreleased runtimes; otherwise throws. */
export function unreleasedRuntime(url) {
  let host;
  try { host = new URL(url).host; } catch { throw new Error(`AVATAR_RUNTIME is not a URL: ${url}`); }
  if (UNRELEASED_HOSTS.includes(host)) return url;
  throw new Error(
    `AVATAR_RUNTIME names ${url}. It may only name an unreleased runtime, on ${UNRELEASED_HOSTS.join(" or ")}. ` +
      `A page reaches a runtime on avatar.voqalize.com by depending on the @voqalize/avatar release that pins it.`,
  );
}

export function avatarRuntime(url = process.env.AVATAR_RUNTIME) {
  if (!url) return null;
  unreleasedRuntime(url);
  return {
    name: "voqalize-avatar-runtime",
    enforce: "pre",
    config: () => ({ optimizeDeps: { exclude: ["@voqalize/avatar"] } }),
    configResolved(config) {
      config.logger.info(`@voqalize/avatar runtime overridden: ${url}`);
    },
    load(id) {
      const path = id.split("?")[0];
      if (!PIN.test(path)) return null;
      const source = readFileSync(path, "utf8");
      if (!URL_LINE.test(source)) throw new Error(`${path}: no RUNTIME_URL to override`);
      return source.replace(URL_LINE, `export const RUNTIME_URL = ${JSON.stringify(url)};`);
    },
  };
}
