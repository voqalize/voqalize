/**
 * Flowforge demo entrypoint — the voice **workflow studio**.
 *
 * An ITSM/HR-ops admin authors and edits Service Request Workflows by talking to
 * "Ada". The studio UI and the voice widget share one `ForgeProvider`, so the
 * copilot and the human drive the same screen; the workflow is a block-based
 * statechart the copilot assembles, tests (real JS guards), and publishes live.
 * Two-way `ui_command` / `state_sync` keeps them in lockstep.
 */

import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { ForgeProvider, useForge } from "./store";
import { Editor, ListView } from "./pages";
import { VoiceLayer } from "./VoiceLayer";
import { ADMIN } from "./data";
import "./styles.css";

function Studio({ presence }: { presence: ReactNode }) {
  const { model } = useForge();
  return (
    <div className="ff-root">
      <div className="ff-topbar">
        <div className="ff-brand">
          <span className="ff-logo">◈</span> Flowforge
          <span className="ff-brand-sub">Workflow Studio</span>
        </div>
        <div className="ff-topbar-right">
          <div className="ff-who">
            {ADMIN.name} · <span>{ADMIN.role}</span>
          </div>
          {presence}
        </div>
      </div>
      {model.view === "list" ? <ListView /> : <Editor />}
    </div>
  );
}

function ForgeDemo() {
  // VoiceLayer owns the session and hands the studio its header presence control,
  // so the copilot is part of the studio's own chrome (top-bar mic + the
  // app-wide ambient presence ring), not a bolted-on widget.
  return (
    <ForgeProvider>
      <VoiceLayer>{(presence) => <Studio presence={presence} />}</VoiceLayer>
    </ForgeProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ForgeDemo />
  </StrictMode>,
);
