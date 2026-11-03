// Links the Site Agent snippet's source into `.platform/` (gitignored), which
// the build and the type check read it from.
//
// The snippet (its watcher, executor, Stage moves and note cards) is the
// platform's and not in this repository; the extension bundles it from a
// checkout of it. VOQALIZE_PLATFORM_DIR names that checkout; without it, the
// first `platform/` beside a parent directory of this one that holds the
// snippet is used (a sibling of this repository's checkout, worktrees
// included).

import { existsSync, lstatSync, readlinkSync, rmSync, symlinkSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SNIPPET = join("frontend", "packages", "site-snippet", "src");

export function platformDir() {
  const named = process.env.VOQALIZE_PLATFORM_DIR;
  if (named) {
    if (!existsSync(join(named, SNIPPET))) throw new Error(`VOQALIZE_PLATFORM_DIR=${named} has no ${SNIPPET}`);
    return resolve(named);
  }
  for (let dir = here; dir !== dirname(dir); dir = dirname(dir)) {
    const candidate = join(dirname(dir), "platform");
    if (existsSync(join(candidate, SNIPPET))) return candidate;
  }
  throw new Error("no platform checkout with the site snippet found; set VOQALIZE_PLATFORM_DIR");
}

export function linkPlatform() {
  const target = platformDir();
  const link = join(here, ".platform");
  let current = null;
  try {
    current = lstatSync(link).isSymbolicLink() ? readlinkSync(link) : "not a link";
  } catch {
    /* no link yet */
  }
  if (current !== target) {
    rmSync(link, { force: true, recursive: true });
    symlinkSync(target, link, "dir");
  }
  return target;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) console.log(`snippet source: ${linkPlatform()}`);
