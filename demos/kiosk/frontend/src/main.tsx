/**
 * Branch-kiosk demo entrypoint — Vantage Bank's credit-card totem.
 *
 * A walk-in customer fills in a short form on the screen, sees the cards ranked
 * for them, and gets a code for the banker's desk. "Tanvi", the hosted `kiosk`
 * brain, runs the form over the `ui-command` / `ui-event` RTVI channels and
 * answers whatever the customer asks along the way.
 *
 * Vantage Bank is invented; so is every card on it.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { KioskApp } from './Kiosk';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <KioskApp />
  </StrictMode>,
);
