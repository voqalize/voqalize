import "@fontsource-variable/fraunces";
import "@fontsource-variable/plus-jakarta-sans";
// Only the Devanagari letters, for the हिंदी toggle and Hindi copy.
import "@fontsource/noto-sans-devanagari/devanagari-400.css";
import "@fontsource/noto-sans-devanagari/devanagari-700.css";
import "./styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
