/**
 * Where the customer stands — a band, its reasons, and an indicative limit.
 *
 * **No number ever appears here that looks like a credit score**, and none is
 * sent: the brain works in bands and reasons, and this screen can only render
 * what it is given. The footnote is not decoration either — the kiosk has no
 * tool that can approve anything, and the line that says a banker confirms it is
 * the honest description of what just happened.
 *
 * One control: the customer says they have read it and asks for the cards.
 * Rohan can move on himself when he is ready, and either way it is the same
 * `show_shortlist` that puts them on screen.
 */

import { COLOR, SIZE } from '../brand';
import type { ShowEligibility } from '../actions.gen';
import { bandLabel, strings, type Language } from '../language';
import { StageTitle, Tag, TouchButton } from '../ui';

export function EligibilityStage({
  language,
  eligibility,
}: {
  language: Language;
  eligibility: ShowEligibility | null;
}) {
  const copy = strings(language);
  if (!eligibility) return null;
  return (
    <div className="kiosk-elig">
      <StageTitle>{copy.eligibilityTitle}</StageTitle>
      <Tag tone="leaf">{bandLabel(eligibility.band, language)}</Tag>

      <ul className="kiosk-elig-reasons">
        {eligibility.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>

      <div className="kiosk-elig-line">
        <span className="kiosk-elig-line-label">{copy.lineLabel}</span>
        <span className="kiosk-elig-line-value">{eligibility.line_estimate}</span>
      </div>

      <p className="kiosk-elig-note">{copy.bankerConfirms}</p>

      <style>{`
        .kiosk-elig { display: flex; flex-direction: column; align-items: flex-start; gap: 14px; }
        .kiosk-elig-reasons {
          margin: 0;
          padding-left: 22px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          font-size: ${SIZE.body}px;
        }
        .kiosk-elig-line {
          display: flex;
          flex-direction: column;
          gap: 2px;
          padding: 14px 18px;
          border-radius: 14px;
          background: rgba(31, 122, 92, 0.10);
        }
        .kiosk-elig-line-label {
          font-size: 15px;
          font-weight: 700;
          letter-spacing: .02em;
          text-transform: uppercase;
          color: ${COLOR.leaf};
        }
        .kiosk-elig-line-value { font-size: ${SIZE.headline}px; font-weight: 800; }
        .kiosk-elig-note { margin: 0; font-size: 17px; color: ${COLOR.muted}; }
      `}</style>
    </div>
  );
}

export function EligibilityControls({
  language,
  onAcknowledge,
}: {
  language: Language;
  onAcknowledge: () => void;
}) {
  return <TouchButton label={strings(language).eligibilityNext} onClick={onAcknowledge} />;
}
