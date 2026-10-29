/**
 * The manifest as it is published: `exports` pointed at the compiled `dist`
 * (`publishConfig.exports`) and `private` dropped.
 *
 * In this repository the package's `exports` point at its TypeScript source,
 * so the demo extensions and the tests run it as written. `npm publish`, which
 * the release uses because npm's trusted publishing is npm's, does not read
 * `publishConfig.exports` the way pnpm does, so the release runs this on its
 * own checkout first. Never run it in a working tree you keep.
 */

import { readFileSync, writeFileSync } from "node:fs";

const path = new URL("../package.json", import.meta.url);
const pkg = JSON.parse(readFileSync(path, "utf8"));
const { exports, ...rest } = pkg.publishConfig ?? {};
if (!exports) throw new Error("package.json has no publishConfig.exports");
pkg.exports = exports;
pkg.publishConfig = rest;
delete pkg.private;
writeFileSync(path, `${JSON.stringify(pkg, null, 2)}\n`);
console.log(`publishing ${pkg.name}@${pkg.version} from dist`);
