import { defineConfig, mergeConfig } from "vitest/config";
import vite from "./vite.config";

// The app's own Vite config (the catalog plugin, the base), with a DOM.
export default mergeConfig(
  vite,
  defineConfig({
    test: {
      environment: "happy-dom",
      include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
      testTimeout: 20000,
    },
  }),
);
