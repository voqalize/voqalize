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

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { OrderDeskProvider } from "./store";
import { OrderDeskApp } from "./pages";

function OrderDeskDemo() {
  return (
    <div className="od-demo-root" style={{ position: "fixed", inset: 0, overflow: "hidden" }}>
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
