import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.tsx"],
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  treeshake: true,
  // The demos bring their own React and their own copy of the SDK.
  external: ["react", "react-dom", "@voqalize/client-react"],
});
