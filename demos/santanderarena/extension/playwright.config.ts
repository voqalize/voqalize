import { defineConfig } from "@playwright/test";

// The built extension (test/.build/ext, a stand-in call) on pages served at
// santanderarena.cl's address by `route` (test/holder.spec.ts). Headless, no
// network.
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
