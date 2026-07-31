/**
 * Aura Bank support demo entrypoint — an ambient L1 banking-support desk.
 *
 * An Aura-branded Help & Support centre with a voice assistant that answers
 * "how do I…" questions by pulling up Aura's own how-to videos, jumping to the
 * exact step, and narrating. The page and the voice layer share one
 * `AuraProvider`, so the assistant and the customer drive the same screen:
 * the agent drives via `ui_command` and stays aware of the on-screen state via
 * a silent `state_sync`. Navigation is React state, so the live call survives
 * screen changes.
 *
 * `AuraAssistant` owns the session and wraps the page, handing its one presence
 * control down as a render-prop — the bank's own header renders it, so the voice
 * affordance reads as product chrome rather than a bolted-on widget.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AuraProvider } from './store';
import { AuraApp } from './pages';
import { AuraAssistant } from './AuraAssistant';

function AuraDemo() {
  return (
    <div style={{ position: 'fixed', inset: 0, overflow: 'hidden' }}>
      <AuraProvider>
        <AuraAssistant>{(presence) => <AuraApp presence={presence} />}</AuraAssistant>
      </AuraProvider>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuraDemo />
  </StrictMode>,
);
