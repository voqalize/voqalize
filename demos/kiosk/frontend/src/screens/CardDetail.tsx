/**
 * One card, in full.
 *
 * `OpenCardDetail` carries a card id and nothing else, because the card's terms
 * are already on the page: the shortlist that put this card on screen brought
 * every display string with it. So this screen looks the card up in the
 * shortlist rather than holding a catalogue of its own — one copy of the terms,
 * and no second place for them to go stale.
 *
 * A card id that is not in the shortlist renders nothing rather than throwing. A
 * page and a brain ship separately, and a branch is a bad place to find that out.
 *
 * Rohan reads none of it aloud. He says which card and why; the totem carries
 * the fee, the cap and the threshold.
 */

import { COLOR } from '../brand';
import type { ShowShortlist } from '../actions.gen';
import { strings, type Language } from '../language';
import { FactRow, StageTitle, Tag, TouchButton } from '../ui';

export function CardDetailStage({
  language,
  cardId,
  shortlist,
}: {
  language: Language;
  cardId: string | null;
  shortlist: ShowShortlist | null;
}) {
  const copy = strings(language);
  const card = shortlist?.cards.find((c) => c.id === cardId);
  if (!card) return null;
  return (
    <div className="kiosk-detail">
      <StageTitle>{card.name}</StageTitle>
      {card.eligible ? <Tag tone="leaf">{copy.likelyEligible}</Tag> : null}
      <FactRow label={copy.rowFee} value={card.fee} />
      <FactRow label={copy.rowWaiver} value={card.waiver} />
      <FactRow label={copy.rowReward} value={card.reward} />
      <FactRow label={copy.rowHero} value={card.perk} />
      <FactRow label={copy.detailNeeds} value={card.requirement} />
      <FactRow label={copy.lineLabel} value={card.line_estimate} />
      <p className="kiosk-detail-note">{copy.bankerConfirms}</p>
      <style>{`
        .kiosk-detail { display: flex; flex-direction: column; align-items: stretch; }
        .kiosk-detail .kiosk-tag { align-self: flex-start; margin-bottom: 10px; }
        .kiosk-detail-note {
          margin: 14px 0 0;
          font-size: 17px;
          line-height: 1.5;
          color: ${COLOR.muted};
        }
      `}</style>
    </div>
  );
}

/**
 * Out of the card and back to the three. `CardDetailClosed` says only that the
 * detail was left; the brain answers it by re-dispatching the shortlist it
 * already holds, with the same payload, so no row moves on the way back.
 */
export function CardDetailControls({
  language,
  onBack,
}: {
  language: Language;
  onBack: () => void;
}) {
  return <TouchButton label={strings(language).detailBack} onClick={onBack} />;
}
