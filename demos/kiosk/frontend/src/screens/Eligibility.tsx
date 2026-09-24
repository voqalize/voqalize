/**
 * Where the customer stands — a band, its reasons, and an indicative limit.
 *
 * **No number ever appears here that looks like a credit score**, and none is
 * sent: the brain works in bands and reasons, and this screen can only render
 * what it is given. The footnote is not decoration either — the kiosk has no
 * tool that can approve anything, and the line that says a banker confirms it is
 * the honest description of what just happened.
 *
 * One control: the customer has read it and wants the cards. Tess moves on by
 * herself when asked out loud, and either way it is the same `show_shortlist`.
 */

import { Check } from '@phosphor-icons/react';
import { COLOR } from '../brand';
import type { ShowEligibility } from '../actions.gen';
import { bandLabel, strings, type Language } from '../language';
import { Tag, TouchButton, TrayTitle } from '../ui';

export function EligibilityTray({
  language,
  eligibility,
  onAcknowledge,
}: {
  language: Language;
  eligibility: ShowEligibility | null;
  onAcknowledge: () => void;
}) {
  const copy = strings(language);
  if (!eligibility) return null;
  return (
    <div className="kiosk-elig">
      <div className="kiosk-elig-head">
        <TrayTitle>{copy.eligibilityTitle}</TrayTitle>
        <Tag tone="leaf">{bandLabel(eligibility.band, language)}</Tag>
      </div>

      <div className="kiosk-elig-line">
        <span className="kiosk-elig-line-label">{copy.lineLabel}</span>
        <span className="kiosk-elig-line-value">{eligibility.line_estimate}</span>
      </div>

      <ul className="kiosk-elig-reasons">
        {eligibility.reasons.map((reason) => (
          <li key={reason}>
            <Check size={18} weight="bold" aria-hidden />
            <span>{reason}</span>
          </li>
        ))}
      </ul>

      <TouchButton label={copy.eligibilityNext} onClick={onAcknowledge} wide />
      <p className="kiosk-note">{copy.bankerConfirms}</p>

      <style>{`
        .kiosk-elig-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
        .kiosk-elig-head .kiosk-tray-title { margin: 0; }
        .kiosk-elig-line { display: grid; gap: 2px; margin-bottom: 14px; }
        .kiosk-elig-line-label { font-size: 14px; font-weight: 500; color: ${COLOR.muted}; }
        .kiosk-elig-line-value { font-size: 24px; font-weight: 700; line-height: 1.2; letter-spacing: -0.015em; color: ${COLOR.brand}; }
        .kiosk-elig-reasons { display: grid; gap: 8px; margin: 0 0 18px; padding: 0; list-style: none; font-size: 16px; }
        .kiosk-elig-reasons li { display: flex; gap: 10px; align-items: flex-start; }
        .kiosk-elig-reasons svg { flex: none; margin-top: 3px; color: ${COLOR.leaf}; }
      `}</style>
    </div>
  );
}
