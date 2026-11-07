import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "happy-dom",
    include: ["test/**/*.test.ts", "builder/**/*.test.ts"],
    // small-webrtc-transport's ESM build imports "lodash/cloneDeep" without an
    // extension, which Node's resolver refuses; bundling it lets Vite resolve it.
    server: { deps: { inline: ["@pipecat-ai/small-webrtc-transport", "@voqalize/client-transport"] } },
  },
});
