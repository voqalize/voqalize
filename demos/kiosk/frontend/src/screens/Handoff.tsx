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
import { StageTitle } from '../ui';
import qrImage from '../assets/handoff-qr.svg';

export function HandoffStage({ language, qr }: { language: Language; qr: ShowQr | null }) {
  const copy = strings(language);
  if (!qr) return null;
  return (
    <div className="kiosk-handoff">
      <StageTitle>{copy.handoffTitle}</StageTitle>
      <img className="kiosk-handoff-code" src={qrImage} alt="" width={200} height={200} />
      <p className="kiosk-handoff-caption">{qr.caption}</p>
      <style>{`
        .kiosk-handoff {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          gap: 14px;
        }
        .kiosk-handoff-code {
          width: min(200px, 44%);
          height: auto;
          padding: 10px;
          border-radius: 14px;
          background: #FFFFFF;
          border: 1px solid ${COLOR.rule};
        }
        .kiosk-handoff-caption {
          margin: 0;
          max-width: 32ch;
          font-size: ${SIZE.body}px;
          color: ${COLOR.muted};
        }
      `}</style>
    </div>
  );
}
