import { defineConfig } from "@playwright/test";

// The adapter against trimmed copies of cannonhome.cl's pages, served at
// their real addresses by `page.route` (test/site.ts). Headless, no network.
export default defineConfig({
  testDir: "test",
  testMatch: /.*\.spec\.ts$/,
  timeout: 45_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    headless: true,
    viewport: { width: 1440, height: 900 },
    locale: "es-CL",
    browserName: "chromium",
  },
});
