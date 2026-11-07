import { defineConfig } from "@playwright/test";

// The component pages (every widget state under a strict CSP, screenshotted)
// and the builder page. `SHOTS_DIR` says where screenshots go (default
// `test-results/shots`). The live suite (`test/e2e`, a real stack) joins only
// when `VQL_E2E_STACK` names one; `npm run test:live` runs it alone.
export default defineConfig({
  globalSetup: "./test/pages/global-setup.ts",
  fullyParallel: true,
  reporter: [["list"]],
  use: { browserName: "chromium", colorScheme: "light", reducedMotion: "reduce" },
  projects: [
    { name: "pages", testDir: "test/pages", testMatch: "*.spec.ts" },
    { name: "builder", testDir: "builder", testMatch: "*.spec.ts" },
    ...(process.env.VQL_E2E_STACK
      ? [{ name: "live", testDir: "test/e2e", testMatch: "*.spec.ts", fullyParallel: false, retries: Number(process.env.VQL_E2E_RETRIES ?? 0), timeout: 120_000 }]
      : []),
  ],
});
