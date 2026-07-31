/**
 * Servicing demo entrypoint — the "Meridian Servicing Console".
 *
 * A mock internal mortgage-servicing console with the "Servicing Desk" voice
 * assistant. The console UI and the voice layer share one `ServicingProvider`,
 * so the assistant and the human advisor drive the same screen; state-based
 * navigation keeps the live call alive across screens. The assistant generates
 * all workup/packet/draft data and stays aware of the live workspace via two-way
 * `ui_command` / `state_sync`.
 *
 * `ServicingDesk` owns the session and hands its one presence control back as a
 * render-prop, which the console mounts in its own top bar — the voice layer is
 * ambient (a full-viewport ring) rather than a docked widget.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ServicingProvider } from "./store";
import { ServicingApp } from "./pages";
import { ServicingDesk } from "./ServicingDesk";

function ServicingDemo() {
  return (
    <div className="sv-demo-root" style={{ position: "fixed", inset: 0, overflow: "hidden" }}>
      <ServicingProvider>
        <ServicingDesk>{(presence) => <ServicingApp presence={presence} />}</ServicingDesk>
      </ServicingProvider>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ServicingDemo />
  </StrictMode>,
);
