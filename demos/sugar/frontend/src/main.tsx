/**
 * Sugar demo entrypoint — "Sugar Coach" daily diabetes check-in.
 *
 * A mock diabetes-care mobile app with the "Sugar Coach" voice agent. The app UI
 * and the in-call bar share one `SugarProvider`, so the coach and the patient
 * drive the same screen; state-based navigation keeps the live call alive across
 * screens. The coach generates all logged data (meals, calories, summaries) and
 * stays aware of the live screen via two-way `ui-command` / `state_sync`.
 */

import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { DemoGate } from "@voqalize/demo-kit";
import { SugarProvider } from "./store";
import { SugarApp } from "./pages";

function SugarDemo() {
  // The gate sits at the root, not around a connect call: this demo opens on a
  // scenario picker and only rings the patient's phone a few taps later, so
  // "join" here uncovers the demo and the microphone opens inside its own flow.
  // The notice still lands before anything is chosen, which is the point.
  const [joined, setJoined] = useState(false);

  return (
    <div className="sugar-demo-root" style={{ position: "fixed", inset: 0, overflow: "hidden" }}>
      <DemoGate
        open={!joined}
        title="Sugar Coach"
        blurb="Pick a patient and a scenario, then answer the call — the coach runs a daily diabetes check-in and logs it on screen as you talk."
        accent="#0E9F6E"
        joinLabel="Start the demo"
        onJoin={() => setJoined(true)}
      />
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
