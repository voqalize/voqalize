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
 * Tess reads none of it aloud. She says which card and why; the tray carries
 * the fee, the cap and the threshold.
 */

import type { ShowShortlist } from '../actions.gen';
import { strings, type Language } from '../language';
import { CardFace, FactList, Tag, TouchButton } from '../ui';

export function CardDetailTray({
  language,
  cardId,
  shortlist,
  onBack,
  onChoose,
}: {
  language: Language;
  cardId: string | null;
  shortlist: ShowShortlist | null;
  onBack: () => void;
  onChoose: (cardId: string) => void;
}) {
  const copy = strings(language);
  const card = shortlist?.cards.find((c) => c.id === cardId);
  if (!card) return null;
  const recommended = card.id === shortlist?.recommended_id;
  return (
    <div className="kiosk-detail">
      <div className="kiosk-slide-head">
        <CardFace card={card} small />
        <div className="kiosk-slide-title">
          <span className="kiosk-slide-name">{card.name}</span>
          <span className="kiosk-slide-tags">
            {recommended ? <Tag tone="accent">{copy.bestForYou}</Tag> : null}
            {card.eligible ? <Tag tone="leaf">{copy.likelyEligible}</Tag> : null}
          </span>
        </div>
      </div>
      <FactList
        rows={[
          [copy.rowFee, card.fee],
          [copy.rowWaiver, card.waiver],
          [copy.rowReward, card.reward],
          [copy.rowHero, card.perk],
          [copy.detailNeeds, card.requirement],
          [copy.lineLabel, card.line_estimate],
        ]}
      />
      <div className="kiosk-row kiosk-detail-actions">
        <TouchButton label={copy.detailBack} tone="quiet" onClick={onBack} />
        <TouchButton label={copy.chooseCard} onClick={() => onChoose(card.id)} ariaLabel={`${copy.chooseCard}: ${card.name}`} />
      </div>
      <p className="kiosk-note">{copy.bankerConfirms}</p>
      <style>{`
        .kiosk-detail { display: grid; gap: 12px; }
        .kiosk-detail .kiosk-slide-head { display: flex; align-items: center; gap: 12px; }
        .kiosk-detail .kiosk-slide-title { display: grid; gap: 5px; min-width: 0; }
        .kiosk-detail .kiosk-slide-name { font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }
        .kiosk-detail .kiosk-slide-tags { display: flex; gap: 6px; flex-wrap: wrap; }
        .kiosk-detail .kiosk-facts { grid-template-columns: 1fr 1fr; column-gap: 16px; }
        .kiosk-detail-actions { margin-top: 4px; }
        .kiosk-detail .kiosk-note { margin: 0; text-align: center; }
      `}</style>
    </div>
  );
}
