import { defineConfig } from "@playwright/test";

// The holder and its pages against small stand-ins for Explora's pages on both
// hosts, served at their real addresses by `context.route` (test/holder.spec.ts).
// Headless, no network.
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
