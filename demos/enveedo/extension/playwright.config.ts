import { defineConfig } from "@playwright/test";

// The holder and its pages, in the test build of the extension, against pages
// served at enveedo.com's address (test/holder.spec.ts and test/meetings.spec.ts). Headless, no network.
export default defineConfig({
  testDir: "test",
  testMatch: /.*\.spec\.ts$/,
  timeout: 45_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    headless: true,
    viewport: { width: 1440, height: 900 },
    locale: "en-US",
    browserName: "chromium",
  },
});
