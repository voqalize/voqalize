/**
 * The three cards, ranked, in a row the customer swipes through.
 *
 * The cards sit in the tray, under Tanvi, and scroll sideways one at a time: a
 * finger flicks, and each card snaps whole into view rather than stopping half
 * way across two. The recommended one is shown first, with the accent on it.
 * Arrows and the position marks do the same for a mouse or a keyboard, and they
 * are real controls, not decoration — each one names the card it shows.
 *
 * Every card carries its two deciding terms — the fee and the rewards — so the
 * row *is* the comparison and there is no separate compare mode; the rest is
 * one tap away in Details. Two
 * controls per card: Details opens it, Choose moves on. They are separate
 * because a card that chose itself when you touched it to read it would be a
 * trap at waist height.
 *
 * Voice leads here as everywhere: "tell me about the fuel one" and "I'll take
 * it" do what the two buttons do, through the same actions.
 *
 * Every term printed here is a display string off the wire. The page owns no
 * product copy: the fee, the cap and the threshold have one source, and it is
 * the brain's card shelf.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { CaretLeft, CaretRight } from '@phosphor-icons/react';
import { COLOR, FOCUS, SIZE } from '../brand';
import type { CardView, ShowShortlist } from '../actions.gen';
import { strings, type Language } from '../language';
import { CardFace, FactList, Tag, TouchButton, VoiceHint } from '../ui';

export interface ShortlistProps {
  language: Language;
  shortlist: ShowShortlist | null;
  onTapCard: (cardId: string) => void;
  onChooseCard: (cardId: string) => void;
}

export function ShortlistTray({ language, shortlist, onTapCard, onChooseCard }: ShortlistProps) {
  const copy = strings(language);
  const track = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const cards = shortlist?.cards ?? [];

  // Which card is in view, from the browser's own intersection bookkeeping —
  // never from a scroll listener.
  useEffect(() => {
    const root = track.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.index));
        }
      },
      { root, threshold: 0.6 },
    );
    root.querySelectorAll('[data-index]').forEach((slide) => observer.observe(slide));
    return () => observer.disconnect();
  }, [cards.length]);

  const show = useCallback((index: number) => {
    const slide = track.current?.querySelector<HTMLElement>(`[data-index="${index}"]`);
    slide?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  }, []);

  if (!shortlist) return null;

  return (
    <div className="kiosk-shortlist">
      {/* Tanvi says why she picked the first one; the tray does not repeat her. */}
      <VoiceHint>{copy.swipeHint}</VoiceHint>

      <div className="kiosk-carousel" ref={track} role="list">
        {cards.map((card, index) => (
          <ShortlistCard
            key={card.id}
            index={index}
            card={card}
            language={language}
            recommended={card.id === shortlist.recommended_id}
            onOpen={() => onTapCard(card.id)}
            onChoose={() => onChooseCard(card.id)}
          />
        ))}
      </div>

      <div className="kiosk-carousel-nav">
        <button
          type="button"
          className="kiosk-carousel-arrow"
          aria-label={copy.previousCard}
          disabled={active === 0}
          onClick={() => show(active - 1)}
        >
          <CaretLeft size={20} weight="bold" aria-hidden />
        </button>
        <span className="kiosk-carousel-marks">
          {cards.map((card, index) => (
            <button
              key={card.id}
              type="button"
              className={index === active ? 'is-on' : ''}
              aria-label={`${copy.showCard}: ${card.name}`}
              aria-current={index === active}
              onClick={() => show(index)}
            />
          ))}
        </span>
        <button
          type="button"
          className="kiosk-carousel-arrow"
          aria-label={copy.nextCard}
          disabled={active === cards.length - 1}
          onClick={() => show(active + 1)}
        >
          <CaretRight size={20} weight="bold" aria-hidden />
        </button>
      </div>

      <style>{`
        .kiosk-carousel {
          display: grid;
          grid-auto-flow: column;
          grid-auto-columns: 84%;
          gap: 12px;
          margin: 0 -20px;
          padding: 4px 20px 6px;
          overflow-x: auto;
          scroll-snap-type: x mandatory;
          scroll-padding: 0 20px;
          overscroll-behavior-x: contain;
          scrollbar-width: none;
        }
        .kiosk-carousel::-webkit-scrollbar { display: none; }
        .kiosk-slide {
          display: grid;
          align-content: start;
          gap: 10px;
          padding: 12px;
          scroll-snap-align: center;
          border-radius: ${SIZE.radius + 4}px;
          border: 1.5px solid ${COLOR.rule};
          background: #FFFFFFF2;
        }
        .kiosk-slide.is-recommended { border-color: ${COLOR.accent}; box-shadow: 0 14px 30px -20px rgba(243, 115, 33, 0.9); }
        .kiosk-slide-head { display: flex; align-items: center; gap: 12px; }
        .kiosk-slide-title { display: grid; gap: 5px; min-width: 0; }
        .kiosk-slide-name { font-size: 18px; font-weight: 700; letter-spacing: -0.01em; }
        .kiosk-slide-tags { display: flex; gap: 6px; flex-wrap: wrap; }
        .kiosk-slide .kiosk-facts { gap: 6px; padding-top: 10px; }
        .kiosk-slide .kiosk-btn { min-height: 52px; font-size: 17px; }

        .kiosk-carousel-nav { display: flex; align-items: center; justify-content: center; gap: 14px; margin-top: 8px; }
        .kiosk-carousel-arrow {
          display: inline-flex; align-items: center; justify-content: center;
          width: 44px; height: 44px;
          border-radius: 50%;
          border: 1px solid ${COLOR.rule};
          background: ${COLOR.surface};
          color: ${COLOR.brand};
          cursor: pointer;
        }
        .kiosk-carousel-arrow:disabled { opacity: .35; cursor: default; }
        .kiosk-carousel-arrow:focus-visible, .kiosk-carousel-marks button:focus-visible {
          outline: 3px solid ${FOCUS.ring}; outline-offset: 2px;
        }
        .kiosk-carousel-marks { display: inline-flex; gap: 4px; }
        .kiosk-carousel-marks button {
          width: 28px; height: 28px; padding: 0;
          border: 0; background: none; cursor: pointer;
          display: inline-flex; align-items: center; justify-content: center;
        }
        .kiosk-carousel-marks button::before {
          content: ""; width: 8px; height: 8px; border-radius: 4px;
          background: ${COLOR.rule};
          transition: width .3s cubic-bezier(0.16, 1, 0.3, 1), background .3s ease;
        }
        .kiosk-carousel-marks button.is-on::before { width: 22px; background: ${COLOR.brand}; }
      `}</style>
    </div>
  );
}

function ShortlistCard({
  index,
  card,
  language,
  recommended,
  onOpen,
  onChoose,
}: {
  index: number;
  card: CardView;
  language: Language;
  recommended: boolean;
  onOpen: () => void;
  onChoose: () => void;
}) {
  const copy = strings(language);
  return (
    <article
      className={`kiosk-slide${recommended ? ' is-recommended' : ''}`}
      data-index={index}
      role="listitem"
      aria-label={card.name}
    >
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
          [copy.rowReward, card.reward],
        ]}
      />
      <div className="kiosk-row">
        <TouchButton label={copy.details} tone="quiet" onClick={onOpen} ariaLabel={`${copy.details}: ${card.name}`} />
        <TouchButton label={copy.chooseCard} onClick={onChoose} ariaLabel={`${copy.chooseCard}: ${card.name}`} />
      </div>
    </article>
  );
}
