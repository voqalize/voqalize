/**
 * Sugar demo entrypoint — "Sugar Coach" daily diabetes check-in.
 *
 * A mock diabetes-care mobile app with the "Sugar Coach" voice agent. The app UI
 * and the in-call bar share one `SugarProvider`, so the coach and the patient
 * drive the same screen; state-based navigation keeps the live call alive across
 * screens. The coach generates all logged data (meals, calories, summaries) and
 * stays aware of the live screen via two-way `ui_command` / `state_sync`.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { SugarProvider } from "./store";
import { SugarApp } from "./pages";

function SugarDemo() {
  return (
    <div className="sugar-demo-root" style={{ position: "fixed", inset: 0, overflow: "hidden" }}>
      <SugarProvider>
        <SugarApp />
      </SugarProvider>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SugarDemo />
  </StrictMode>,
);
