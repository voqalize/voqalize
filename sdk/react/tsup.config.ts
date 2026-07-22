import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  treeshake: true,
  // Keep peers external — consumers bring their own React + pipecat client.
  external: [
    "react",
    "react-dom",
    "@pipecat-ai/client-js",
    "@pipecat-ai/client-react",
  ],
});
