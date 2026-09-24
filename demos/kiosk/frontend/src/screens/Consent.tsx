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

import { ArrowRight } from '@phosphor-icons/react';
import { COLOR } from '../brand';
import type { OpenConsent, ShowShortlist } from '../actions.gen';
import { strings, type Language } from '../language';
import { CardFace, TouchButton, TrayTitle } from '../ui';

export function ConsentTray({
  language,
  consent,
  shortlist,
  onConsent,
}: {
  language: Language;
  consent: OpenConsent | null;
  shortlist: ShowShortlist | null;
  onConsent: (cardId: string) => void;
}) {
  const copy = strings(language);
  if (!consent) return null;
  const card = shortlist?.cards.find((c) => c.id === consent.card_id);
  return (
    <div className="kiosk-consent">
      <TrayTitle>{copy.consentTitle}</TrayTitle>
      {card ? (
        <div className="kiosk-consent-card">
          <CardFace card={card} compact />
          <span>{card.name}</span>
        </div>
      ) : null}
      <ul className="kiosk-consent-list">
        {consent.bullets.map((bullet) => (
          <li key={bullet}>
            <ArrowRight size={16} weight="bold" aria-hidden />
            <span>{bullet}</span>
          </li>
        ))}
      </ul>
      <TouchButton label={copy.consentAgree} onClick={() => onConsent(consent.card_id)} wide />
      <p className="kiosk-note kiosk-consent-hint">{copy.consentHint} {copy.bankerConfirms}</p>
      <style>{`
        .kiosk-consent-card { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: 18px; font-weight: 600; }
        .kiosk-consent-list { display: grid; gap: 8px; margin: 0 0 18px; padding: 0; list-style: none; font-size: 16px; }
        .kiosk-consent-list li { display: flex; gap: 10px; align-items: flex-start; }
        .kiosk-consent-list svg { flex: none; margin-top: 4px; color: ${COLOR.brand}; }
        .kiosk-consent-hint { text-align: center; }
      `}</style>
    </div>
  );
}
