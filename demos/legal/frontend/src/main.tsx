/**
 * Legal demo entrypoint — "Docket", an ambient contract-review desk.
 *
 * In-house counsel reviews a Master Services Agreement while an ambient voice
 * copilot follows along on the same screen — pointing at clauses, proposing
 * redlines, fanning out background diligence, and extracting obligations. The
 * document view and the voice layer share one `LegalProvider`, so the assistant
 * and the lawyer work the same document; the assistant drives the screen via
 * `ui_command` and stays aware of the reading position via silent `clause_focus`.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { LegalProvider } from "./store";
import { LegalDesk } from "./LegalDesk";

function LegalDemo() {
  return (
    <LegalProvider>
      <LegalDesk />
    </LegalProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LegalDemo />
  </StrictMode>,
);
