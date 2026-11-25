import "@fontsource-variable/bodoni-moda";
import "@fontsource-variable/manrope";
import "./styles/tokens.css";
import "./styles/shell.css";
import "./styles/dock.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
