import "@fontsource-variable/fraunces/full.css";
import "@fontsource-variable/hanken-grotesk/index.css";
import "@fontsource-variable/noto-sans-devanagari/index.css";
import "./styles/base.css";
import "./styles/site.css";
import "./styles/pages.css";
import "./styles/dock.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
