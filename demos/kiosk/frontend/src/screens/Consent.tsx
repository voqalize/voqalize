/**
 * What happens next, and what does not.
 *
 * The bullets come from the brain, written in Python rather than by the model.
 * The last line is the page's, and it is the one that matters: **this kiosk
 * approves nothing and submits nothing.** It has no tool that could. Agreeing
 * here means a banker at the desk picks the conversation up — which is why the
 * button says "I agree" and not "Apply".
 *
 * The consent is given out loud in the ordinary run; the button is the fallback
 * for a customer who would rather press it, and it is not a gate in front of
 * anything.
 */

import { COLOR, SIZE } from '../brand';
import type { OpenConsent, ShowShortlist } from '../actions.gen';
import { strings, type Language } from '../language';
import { StageTitle, TouchButton } from '../ui';

export function ConsentStage({
  language,
  consent,
  shortlist,
}: {
  language: Language;
  consent: OpenConsent | null;
  shortlist: ShowShortlist | null;
}) {
  const copy = strings(language);
  if (!consent) return null;
  const card = shortlist?.cards.find((c) => c.id === consent.card_id);
  return (
    <div className="kiosk-consent">
      <StageTitle>{copy.consentTitle}</StageTitle>
      {card ? <p className="kiosk-consent-card">{card.name}</p> : null}
      <ul className="kiosk-consent-list">
        {consent.bullets.map((bullet) => (
          <li key={bullet}>{bullet}</li>
        ))}
      </ul>
      <p className="kiosk-consent-note">{copy.bankerConfirms}</p>
      <style>{`
        .kiosk-consent { display: flex; flex-direction: column; gap: 12px; }
        .kiosk-consent-card { margin: 0; font-size: ${SIZE.headline}px; font-weight: 800; }
        .kiosk-consent-list {
          margin: 0;
          padding-left: 22px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          font-size: ${SIZE.body}px;
        }
        .kiosk-consent-note { margin: 0; font-size: 17px; color: ${COLOR.muted}; }
      `}</style>
    </div>
  );
}

export function ConsentControls({
  language,
  consent,
  onConsent,
}: {
  language: Language;
  consent: OpenConsent | null;
  onConsent: (cardId: string) => void;
}) {
  if (!consent) return null;
  return (
    <TouchButton label={strings(language).consentAgree} onClick={() => onConsent(consent.card_id)} />
  );
}
