/**
 * Travel demo entrypoint — "Trip Studio".
 *
 * A mock B2B itinerary planner with the "Travel Desk" voice agent. The portal UI
 * and the voice widget share one `TravelProvider`, so the agent and the human
 * travel agent drive the same screen; state-based navigation keeps the live call
 * alive across screens. The agent generates all flight/hotel/activity data and
 * stays aware of the active itinerary via two-way `ui_command` / `state_sync`.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { TravelProvider } from "./store";
import { TravelApp } from "./pages";
import { TravelAdvisor } from "./TravelAdvisor";

function TravelDemo() {
  return (
    <div className="tv-demo-root" style={{ position: "fixed", inset: 0, overflow: "hidden" }}>
      <TravelProvider>
        <TravelApp />
        <TravelAdvisor />
      </TravelProvider>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <TravelDemo />
  </StrictMode>,
);
