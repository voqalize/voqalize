/**
 * Petwell demo entrypoint — a vet hospital chain's website with Tushar, its AI
 * front desk, docked in the corner.
 *
 * The site and the voice layer share one `SiteProvider`, so Tushar and the
 * visitor drive the same pages, booking panel and language; state-based
 * navigation keeps the live call alive across all of them.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { SiteProvider } from './store';
import { Site } from './site';
import { PetwellDesk } from './PetwellDesk';

function PetwellDemo() {
  return (
    <div className="pw-demo-root" style={{ position: 'fixed', inset: 0, overflow: 'hidden' }}>
      <SiteProvider>
        <PetwellDesk>
          {(dock) => <Site dock={dock} />}
        </PetwellDesk>
      </SiteProvider>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PetwellDemo />
  </StrictMode>,
);
