/**
 * Branch-kiosk demo entrypoint — Vantage Bank's credit-card totem.
 *
 * A walk-in customer answers four questions out loud, sees three cards ranked
 * for them, confirms by voice, and gets a code for the banker's desk. "Tess",
 * the hosted `kiosk` brain, drives the screen over the `ui-command` / `ui-event`
 * RTVI channels.
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
