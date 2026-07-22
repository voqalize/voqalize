/**
 * Shopping demo entrypoint — "Voqal Mobile".
 *
 * A mock mobile-phone store with the "Mobile Expert" voice agent. The store UI
 * and the voice widget share one `MobileShopProvider`, so the agent and the
 * shopper drive the same screen; state-based navigation keeps the live call
 * alive across screens. The agent drives the page via `ui_command` messages.
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
        <MobileShopApp />
        <MobileExpert />
      </MobileShopProvider>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ShoppingDemo />
  </StrictMode>,
);
