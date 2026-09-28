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
 * The shim is kept out of dependency pre-bundling while overridden, because
 * the pre-bundler reads `pin.js` without running plugins.
 */
import { readFileSync } from "node:fs";

const PIN = /[\\/]@voqalize[\\/]avatar[\\/]dist[\\/]pin\.js$/;
const URL_LINE = /export const RUNTIME_URL = "[^"]*";/;

export function avatarRuntime(url = process.env.AVATAR_RUNTIME) {
  if (!url) return null;
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
