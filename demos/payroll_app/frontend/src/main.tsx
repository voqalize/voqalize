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
  // `__tkFakeCall("speaking")` shows the call tile without a client; `__tkFakeCall(false)` ends it.
  void import("./voice/fake").then(({ useFakeCall }) => {
    (window as unknown as { __tkFakeCall: (state: string | false) => void }).__tkFakeCall = (state) =>
      useFakeCall.setState(state === false ? { on: false } : { on: true, state: (state || "listening") as "listening" });
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
