import { defineConfig } from "@playwright/test";

// The component pages: every widget state under a strict CSP, screenshotted.
// `SHOTS_DIR` says where the screenshots go (default `test-results/shots`).
export default defineConfig({
  testDir: "test/pages",
  testMatch: "*.spec.ts",
  globalSetup: "./test/pages/global-setup.ts",
  fullyParallel: true,
  reporter: [["list"]],
  use: { browserName: "chromium", colorScheme: "light", reducedMotion: "reduce" },
});
