/**
 * Petwell demo entrypoint — the "Appointment Desk".
 *
 * A vet hospital's booking page with a voice agent that books the visit with
 * the caller: clinic or home, city and branch, reason, a time, and the owner's
 * details — then the caller taps Send Request. The page and the voice layer
 * share one `BookingProvider`, so the agent and the caller drive the same
 * screen; state-based navigation keeps the live call alive across steps.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BookingProvider } from './store';
import { BookingApp } from './pages';
import { PetwellDesk } from './PetwellDesk';

function PetwellDemo() {
  return (
    <div className="pw-demo-root" style={{ position: 'fixed', inset: 0, overflow: 'hidden' }}>
      <BookingProvider>
        <PetwellDesk>{(presence) => <BookingApp presence={presence} />}</PetwellDesk>
      </BookingProvider>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PetwellDemo />
  </StrictMode>,
);
