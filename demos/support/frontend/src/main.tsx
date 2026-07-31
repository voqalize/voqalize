/**
 * Support demo entrypoint — the "Returns Assistant".
 *
 * A mock consumer storefront (past orders) with the "Returns Assistant" voice
 * agent. The store UI and the voice layer share one `OrdersProvider`, so the
 * agent and the shopper drive the same screen; state-based navigation keeps the
 * live call alive across pages. The agent walks the shopper through identifying
 * an item, troubleshooting it, verifying a photo, and filing a return via two-way
 * `ui_command` / `photo_upload` / `return_submitted`.
 *
 * `ReturnsAssistant` owns the session and paints the ambient presence ring; it
 * hands the storefront its one small presence control, which `OrdersApp` mounts
 * in its own top bar.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { OrdersProvider } from "./store";
import { OrdersApp } from "./pages";
import { ReturnsAssistant } from "./ReturnsAssistant";

function SupportDemo() {
  return (
    <div className="os-demo-root" style={{ position: "fixed", inset: 0, overflow: "hidden" }}>
      <OrdersProvider>
        <ReturnsAssistant>{(presence) => <OrdersApp presence={presence} />}</ReturnsAssistant>
      </OrdersProvider>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SupportDemo />
  </StrictMode>,
);
