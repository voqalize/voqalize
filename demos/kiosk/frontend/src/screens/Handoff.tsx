/**
 * The last screen: a code to show at the desk.
 *
 * The image is a **static, pre-generated SVG** checked in beside this file. There
 * is no QR library in this app and there should not be one: the kiosk encodes
 * nothing per customer — the banker scans a fixed branch endpoint and picks the
 * conversation up from there — so a runtime encoder would be a dependency
 * earning its keep by drawing the same picture every time.
 *
 * The caption is the brain's, in the call's language.
 */

import { COLOR, SIZE } from '../brand';
import type { ShowQr } from '../actions.gen';
import { strings, type Language } from '../language';
import { TrayTitle } from '../ui';
import qrImage from '../assets/handoff-qr.svg';

export function HandoffTray({ language, qr }: { language: Language; qr: ShowQr | null }) {
  const copy = strings(language);
  if (!qr) return null;
  return (
    <div className="kiosk-handoff">
      <img className="kiosk-handoff-code" src={qrImage} alt="" width={168} height={168} />
      <div>
        <TrayTitle>{copy.handoffTitle}</TrayTitle>
        <p className="kiosk-handoff-caption">{qr.caption}</p>
      </div>
      <style>{`
        .kiosk-handoff { display: flex; align-items: center; gap: 18px; }
        .kiosk-handoff-code {
          width: 132px;
          height: auto;
          flex: none;
          padding: 8px;
          border-radius: ${SIZE.radius}px;
          background: #FFFFFF;
          border: 1px solid ${COLOR.rule};
        }
        .kiosk-handoff .kiosk-tray-title { margin-bottom: 6px; }
        .kiosk-handoff-caption { margin: 0; font-size: 16px; color: ${COLOR.muted}; }
      `}</style>
    </div>
  );
}
