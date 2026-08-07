/**
 * OrderDesk demo entrypoint — MedSetu B2B order intake over voice.
 *
 * A distributor's ordering app with the MedSetu order desk on the line: the
 * pharmacist gets a 9 AM push, joins a Hindi call, and speaks a bulk order. Every
 * spoken line lands as a free-text row, resolves against the real SKU catalog, and
 * walks a visible state machine to a confirmed SKU — pills and option cards where
 * the catalog is ambiguous, one short question where it isn't enough.
 *
 * The screen and the call share one `OrderDeskProvider`, so agent-driven rows and
 * hand-tapped edits are the same cart: `ui_command` in, `state_sync` out.
 */

import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { DemoGate } from "@voqalize/demo-kit";
import { OrderDeskProvider } from "./store";
import { OrderDeskApp } from "./pages";
import { SAFFRON } from "./theme";

function OrderDeskDemo() {
  // Root-level, for the same reason as Sugar: the demo opens on a pharmacy
  // picker and the call only starts once one is chosen, so joining here just
  // uncovers the demo — the microphone opens later, inside the demo's own flow.
  const [joined, setJoined] = useState(false);

  return (
    <div className="od-demo-root" style={{ position: "fixed", inset: 0, overflow: "hidden" }}>
      <DemoGate
        open={!joined}
        title="MedSetu Order Desk"
        blurb="Pick a pharmacy and answer the call, then speak a bulk medicine order in Hindi or English and watch every line resolve to a real SKU on screen."
        accent={SAFFRON}
        joinLabel="Start the demo"
        onJoin={() => setJoined(true)}
      />
      <OrderDeskProvider>
        <OrderDeskApp />
      </OrderDeskProvider>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <OrderDeskDemo />
  </StrictMode>,
);
