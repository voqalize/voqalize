/**
 * The idle screen — what the totem shows a branch nobody is standing at yet.
 *
 * Two ways in, and the cue names both. Rohan greets whoever walks up, so
 * answering him is the short one; Begin is for the customer who would rather
 * not talk to a machine in a lobby, and it is the first rung of a journey that
 * can be finished without saying a word. Pressing it is an answer to the
 * greeting, not a way around it — the call is live either way.
 */

import { COLOR, SIZE } from '../brand';
import { strings, type Language } from '../language';
import { StageTitle, TouchButton } from '../ui';

export function AttractStage({ language }: { language: Language }) {
  const copy = strings(language);
  return (
    <div className="kiosk-attract">
      <StageTitle>{copy.attractTitle}</StageTitle>
      <p className="kiosk-attract-body">{copy.attractBody}</p>
      <p className="kiosk-attract-cue">
        <span className="kiosk-attract-pip" aria-hidden />
        {copy.attractCue}
      </p>
      <style>{`
        .kiosk-attract {
          display: flex;
          flex-direction: column;
          justify-content: center;
          height: 100%;
          gap: 14px;
        }
        .kiosk-attract-body {
          margin: 0;
          max-width: 34ch;
          font-size: ${SIZE.body}px;
          color: ${COLOR.muted};
        }
        .kiosk-attract-cue {
          display: flex;
          align-items: center;
          gap: 12px;
          margin: 8px 0 0;
          font-size: ${SIZE.body}px;
          font-weight: 700;
          color: ${COLOR.amber};
        }
        .kiosk-attract-pip {
          width: 14px;
          height: 14px;
          flex: none;
          border-radius: 50%;
          background: ${COLOR.amber};
          animation: kiosk-attract-breathe 2.4s ease-in-out infinite;
        }
        @keyframes kiosk-attract-breathe {
          0%, 100% { transform: scale(1); opacity: .55; }
          50% { transform: scale(1.35); opacity: 1; }
        }
        @media (prefers-reduced-motion: reduce) {
          .kiosk-attract-pip { animation: none; opacity: 1; }
        }
      `}</style>
    </div>
  );
}

/** The way in for a hand. The event is what moves the screen; this button only sends it. */
export function AttractControls({
  language,
  onBegin,
}: {
  language: Language;
  onBegin: () => void;
}) {
  return <TouchButton label={strings(language).attractBegin} onClick={onBegin} />;
}
