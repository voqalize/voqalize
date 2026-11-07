import { defineConfig } from "@playwright/test";

// The component pages (every widget state under a strict CSP, screenshotted)
// and the builder page. `SHOTS_DIR` says where screenshots go (default
// `test-results/shots`).
export default defineConfig({
  globalSetup: "./test/pages/global-setup.ts",
  fullyParallel: true,
  reporter: [["list"]],
  use: { browserName: "chromium", colorScheme: "light", reducedMotion: "reduce" },
  projects: [
    { name: "pages", testDir: "test/pages", testMatch: "*.spec.ts" },
    { name: "builder", testDir: "builder", testMatch: "*.spec.ts" },
  ],
});
