import "@fontsource-variable/fraunces/opsz.css";
import "@fontsource-variable/plus-jakarta-sans/index.css";
import "@fontsource-variable/jetbrains-mono/index.css";
import "@fontsource-variable/noto-sans-devanagari/index.css";
import "./styles/app.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { registerMoves } from "./stage/performers";
import { moves } from "./stage/runtime";
import { debugMode } from "./voice/debug";

// Every move, registered once at start, whether or not a call ever happens.
registerMoves(moves);
if (debugMode()) {
  let n = 0;
  (window as unknown as { __tkRun: (id: string, args: unknown) => unknown }).__tkRun = (id, args) => moves.run(id, args, `debug-${++n}`);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
