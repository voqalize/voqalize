import "@fontsource-variable/fraunces/opsz.css";
import "@fontsource-variable/inter-tight/index.css";
import "@fontsource-variable/noto-sans-devanagari/index.css";
import "./styles/base.css";
import "./styles/app.css";
import "./styles/quote.css";
import "./styles/policy.css";
import "./styles/claim.css";
import "./styles/voice.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
