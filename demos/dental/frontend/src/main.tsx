import "@fontsource/young-serif/400.css";
import "@fontsource-variable/instrument-sans/index.css";
// ₹ and Devanagari (हिंदी): neither display face has them, so a self-hosted fallback does.
import "@fontsource/noto-sans-devanagari/devanagari-400.css";
import "@fontsource/noto-sans-devanagari/devanagari-600.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/pages.css";
import "./styles/calendar.css";
import "./styles/voice.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
