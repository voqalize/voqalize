/**
 * Flowforge demo entrypoint — the voice **workflow studio**.
 *
 * An ITSM/HR-ops admin authors and edits Service Request Workflows by talking to
 * "Ada". The studio UI and the voice widget share one `ForgeProvider`, so the
 * copilot and the human drive the same screen; the workflow is a block-based
 * statechart the copilot assembles, tests (real JS guards), and publishes live.
 * Two-way `ui_command` / `state_sync` keeps them in lockstep.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ForgeProvider, useForge } from "./store";
import { Editor, ListView } from "./pages";
import { ForgeAssistant } from "./ForgeAssistant";
import { ADMIN } from "./data";
import "./styles.css";

function Studio() {
  const { model } = useForge();
  return (
    <div className="ff-root">
      <div className="ff-topbar">
        <div className="ff-brand">
          <span className="ff-logo">◈</span> Flowforge
          <span className="ff-brand-sub">Workflow Studio</span>
        </div>
        <div className="ff-who">
          {ADMIN.name} · <span>{ADMIN.role}</span>
        </div>
      </div>
      {model.view === "list" ? <ListView /> : <Editor />}
    </div>
  );
}

function ForgeDemo() {
  return (
    <ForgeProvider>
      <Studio />
      <ForgeAssistant />
    </ForgeProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ForgeDemo />
  </StrictMode>,
);
