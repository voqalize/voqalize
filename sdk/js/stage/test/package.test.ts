/** The manifest npm publishes as written: npm 11 drops a `bin` entry whose
 *  path starts `./` (`@voqalize/stage@0.1.0-rc.1` nearly shipped without its
 *  `stage` command). */

import { describe, expect, it } from "vitest";

import manifest from "../package.json?raw";

describe("package.json", () => {
  it("names each bin by a plain relative path", () => {
    const bin = (JSON.parse(manifest) as { bin: Record<string, string> }).bin;
    expect(Object.keys(bin)).toEqual(["stage"]);
    for (const path of Object.values(bin)) expect(path).toMatch(/^[a-z][\w/.-]*\.mjs$/);
  });

  // npm refuses a provenance-signed publish whose repository does not match the
  // repository that built it (0.1.0-rc.2's first publish: E422).
  it("names the repository the release workflow builds it in", () => {
    const { repository } = JSON.parse(manifest) as { repository?: { url?: string; directory?: string } };
    expect(repository?.url).toBe("git+https://github.com/voqalize/voqalize.git");
    expect(repository?.directory).toBe("sdk/js/stage");
  });
});
