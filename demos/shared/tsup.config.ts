import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.tsx"],
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  treeshake: true,
  // The demos bring their own React and their own pipecat client.
  external: ["react", "react-dom", "@pipecat-ai/client-js"],
});
