import { defineConfig, mergeConfig } from "vitest/config";
import vite from "./vite.config";

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
