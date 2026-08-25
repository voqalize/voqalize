/**
 * Shopping demo entrypoint — "Voqal Mobile".
 *
 * A mock mobile-phone store with the "Mobile Expert" voice agent. The store UI
 * and the voice layer share one `MobileShopProvider`, so the agent and the
 * shopper drive the same screen; state-based navigation keeps the live call
 * alive across screens. The agent drives the page via `ui-command` RTVI events.
 *
 * `MobileExpert` owns the session and hands its one presence control back up as
 * a render-prop, so the store keeps ownership of its own top bar — the voice
 * layer is ambient (a ring around the whole page) plus one button in the chrome,
 * never a docked panel.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MobileShopProvider } from "./store";
import { MobileShopApp } from "./pages";
import { MobileExpert } from "./MobileExpert";

function ShoppingDemo() {
  return (
    <div
      className="ms-root"
      style={{
        position: "fixed",
        inset: 0,
        background: "#f3f4f6",
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        overflow: "hidden",
      }}
    >
      <MobileShopProvider>
        <MobileExpert>{(presence) => <MobileShopApp presence={presence} />}</MobileExpert>
      </MobileShopProvider>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ShoppingDemo />
  </StrictMode>,
);
