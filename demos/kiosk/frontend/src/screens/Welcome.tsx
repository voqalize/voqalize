/**
 * The first screen, before the call.
 *
 * **One way in, and it is the Start button.** The gate in front of the kiosk is
 * that button: pressing it opens the call, and Tess's greeting is the first
 * thing that happens after it. Nothing here offers a second way to begin, so a
 * customer never has to work out whether to speak or to tap.
 *
 * So this tray exists only behind the gate, saying what the kiosk is for. Once
 * the call is up there is no tray at all until the first question: Tess has
 * asked for a name, and if none comes the first question's answers come up by
 * themselves.
 */

import { COLOR } from '../brand';
import { strings, type Language } from '../language';
import { TrayTitle } from '../ui';

export function WelcomeTray({ language }: { language: Language }) {
  const copy = strings(language);
  return (
    <div className="kiosk-welcome">
      <TrayTitle>{copy.attractTitle}</TrayTitle>
      <p className="kiosk-welcome-body">{copy.attractBody}</p>
      <style>{`
        .kiosk-welcome-body { margin: 0; max-width: 34ch; font-size: 17px; color: ${COLOR.muted}; }
      `}</style>
    </div>
  );
}
