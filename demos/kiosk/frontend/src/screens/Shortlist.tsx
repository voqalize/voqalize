/**
 * The three cards, ranked, with the one Rohan leads on lifted out of the stack.
 *
 * **A row never moves when you tap it.** The comparison rows unfold *inside* the
 * row, below its header, so the name a finger was aimed at is still under that
 * finger afterwards. Rows below it move; the tapped one does not. A list that
 * re-sorts or re-centres on tap is the one interaction a totem cannot afford,
 * because the customer is reading it standing up.
 *
 * Tapping also tells Rohan (`CardTapped`), and he may answer by opening the full
 * detail screen. The local unfold is not a bet on that — it is the answer the
 * finger gets in the same frame it lands.
 *
 * Choosing is a second control, not a second meaning for the first: a row that
 * chose a card when you tapped it to read it would be a trap at waist height.
 * So every row carries its own Choose button, always visible so the row's height
 * never depends on what is open, and `CardChosen` is what the brain answers with
 * the consent panel.
 *
 * Every term printed here is a display string off the wire. The page owns no
 * product copy: the fee, the cap and the threshold have one source, and it is
 * the brain's card shelf.
 */

import { useState } from 'react';
import { COLOR, FOCUS, SIZE } from '../brand';
import type { CardView, ShowShortlist } from '../actions.gen';
import { strings, type Language } from '../language';
import { FactRow, StageTitle, Tag, TouchButton } from '../ui';

export interface ShortlistProps {
  language: Language;
  shortlist: ShowShortlist | null;
  /** Set by the lower band's Compare button: every row unfolds at once. */
  comparing: boolean;
  onTapCard: (cardId: string) => void;
  onChooseCard: (cardId: string) => void;
}

export function ShortlistStage({
  language,
  shortlist,
  comparing,
  onTapCard,
  onChooseCard,
}: ShortlistProps) {
  const copy = strings(language);
  // Which single row is unfolded. Local, because one row being open is not a
  // fact about the conversation — comparing all three is, so that one lives in
  // the store where both bands can reach it.
  const [openId, setOpenId] = useState<string | null>(null);
  if (!shortlist) return null;

  const open = (card: CardView) => {
    setOpenId((current) => (current === card.id ? null : card.id));
    onTapCard(card.id);
  };

  return (
    <div className="kiosk-shortlist">
      <StageTitle>{copy.shortlistTitle}</StageTitle>
      <p className="kiosk-shortlist-why">{shortlist.why}</p>

      {shortlist.cards.map((card) => (
        <ShortlistRow
          key={card.id}
          card={card}
          language={language}
          recommended={card.id === shortlist.recommended_id}
          open={comparing || openId === card.id}
          onOpen={() => open(card)}
          onChoose={() => onChooseCard(card.id)}
        />
      ))}

      <p className="kiosk-shortlist-hint">{copy.tapToExpand}</p>

      <style>{`
        .kiosk-shortlist { display: flex; flex-direction: column; gap: 12px; }
        .kiosk-shortlist-why { margin: 0 0 4px; font-size: ${SIZE.body}px; color: ${COLOR.muted}; }
        .kiosk-shortlist-hint { margin: 4px 0 0; font-size: 16px; color: ${COLOR.muted}; }

        .kiosk-card {
          border-radius: 16px;
          border: 2px solid ${COLOR.rule};
          background: #FFFFFF;
          overflow: hidden;
        }
        /* The lift is a property of the recommendation, not of the tap — it does
           not move when the row unfolds. */
        .kiosk-card.is-recommended {
          border-color: ${COLOR.amber};
          box-shadow: 0 10px 28px rgba(232, 133, 11, 0.22);
        }
        .kiosk-row {
          display: block;
          width: 100%;
          padding: 16px 18px;
          border: 0;
          background: transparent;
          font: inherit;
          text-align: left;
          color: inherit;
          cursor: pointer;
        }
        .kiosk-row:focus-visible { outline: 3px solid ${FOCUS.ring}; outline-offset: -3px; }
        /* Always present, so unfolding a row moves the rows below it and nothing
           inside it. Full width because a finger arriving at a totem is aimed at
           a card, not at a word. */
        .kiosk-row-choose {
          display: block;
          width: 100%;
          min-height: ${SIZE.touch}px;
          padding: 0 18px;
          border: 0;
          border-top: 1px solid ${COLOR.rule};
          background: rgba(232, 133, 11, 0.10);
          color: ${COLOR.umber};
          font: inherit;
          font-size: ${SIZE.body}px;
          font-weight: 700;
          text-align: left;
          cursor: pointer;
        }
        .kiosk-row-choose:hover { background: rgba(232, 133, 11, 0.20); }
        .kiosk-row-choose:focus-visible { outline: 3px solid ${FOCUS.ring}; outline-offset: -3px; }
        .kiosk-row-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
        .kiosk-row-name { font-size: ${SIZE.headline}px; font-weight: 800; }
        .kiosk-row-facts { display: block; margin-top: 12px; border-top: 1px solid ${COLOR.rule}; }
        .kiosk-ribbon {
          display: inline-flex;
          padding: 5px 12px;
          border-radius: 999px;
          background: ${COLOR.amber};
          color: ${COLOR.umber};
          font-size: 15px;
          font-weight: 800;
        }
      `}</style>
    </div>
  );
}

/**
 * Two controls, one card: open it to read, choose it to move on. Tab reaches
 * them in that order, which is the order they are read in.
 */
function ShortlistRow({
  card,
  language,
  recommended,
  open,
  onOpen,
  onChoose,
}: {
  card: CardView;
  language: Language;
  recommended: boolean;
  open: boolean;
  onOpen: () => void;
  onChoose: () => void;
}) {
  const copy = strings(language);
  return (
    <div className={`kiosk-card${recommended ? ' is-recommended' : ''}`}>
      <button type="button" className="kiosk-row" aria-expanded={open} onClick={onOpen}>
        <span className="kiosk-row-head">
          <span className="kiosk-row-name">{card.name}</span>
          {recommended ? <span className="kiosk-ribbon">{copy.bestForYou}</span> : null}
          {card.eligible ? <Tag tone="leaf">{copy.likelyEligible}</Tag> : null}
        </span>
        {open ? (
          <span className="kiosk-row-facts">
            <FactRow label={copy.rowFee} value={card.fee} />
            <FactRow label={copy.rowWaiver} value={card.waiver} />
            <FactRow label={copy.rowReward} value={card.reward} />
            <FactRow label={copy.rowHero} value={card.perk} />
          </span>
        ) : null}
      </button>
      {/* Three rows, three identically worded buttons — the card's name is what
          tells a screen reader which one this is. */}
      <button
        type="button"
        className="kiosk-row-choose"
        aria-label={`${copy.chooseCard}: ${card.name}`}
        onClick={onChoose}
      >
        {copy.chooseCard}
      </button>
    </div>
  );
}

export function ShortlistControls({
  language,
  onCompare,
}: {
  language: Language;
  onCompare: () => void;
}) {
  return <TouchButton label={strings(language).compareAll} onClick={onCompare} />;
}
