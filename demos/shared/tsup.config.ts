import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.tsx"],
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  treeshake: true,
  // The demos bring their own React, their own pipecat client and transport,
  // and their own pin of the media manager.
  external: [
    "react",
    "react-dom",
    "@pipecat-ai/client-js",
    "@pipecat-ai/small-webrtc-transport",
    "@voqalize/client-transport",
  ],
});
