import { defineConfig } from "@playwright/test";

// The holder and its pages, end to end in the built extension, with pages
// served at the university's addresses by `route`. Headless, no network.
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
