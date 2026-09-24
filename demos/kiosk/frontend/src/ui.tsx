/**
 * The kiosk's touch primitives.
 *
 * Every size in here is a standing-up-at-a-totem size: 60px is the floor for
 * anything a finger lands on, 18px the floor for anything read at arm's length.
 * Nothing shrinks below that on a phone — the layout gives up columns first.
 *
 * One shape rule, everywhere: lifted things are `SIZE.radius`, small status
 * marks are pills. One accent, spent only on "this one" — a picked answer, the
 * recommended card, a live microphone. Buttons are maroon, never the accent.
 *
 * The rules live in one {@link UiStyles} block that the totem renders once, so
 * the primitives themselves stay class-thin.
 */

import type { ReactNode } from 'react';
import { Check, CheckCircle, Microphone } from '@phosphor-icons/react';
import type { CardView, ConfirmValue } from './actions.gen';
import { CARD_FACE, CARD_FACE_FALLBACK, COLOR, FOCUS, SIZE } from './brand';
import { fieldLabel, strings, type Language } from './language';

/** A button. `primary` moves the journey on; `quiet` is the way sideways. */
export function TouchButton({
  label,
  onClick,
  tone = 'primary',
  wide,
  disabled,
  ariaLabel,
}: {
  label: string;
  onClick: () => void;
  tone?: 'primary' | 'quiet';
  /** Fill the row. The one button on a screen is wide; a pair splits the row. */
  wide?: boolean;
  disabled?: boolean;
  ariaLabel?: string;
}) {
  return (
    <button
      type="button"
      className={`kiosk-btn is-${tone}${wide ? ' is-wide' : ''}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
    >
      {label}
    </button>
  );
}

/**
 * The line above anything a hand could do instead: the microphone first, the
 * tap second. It is the kiosk telling the customer, every time, that speaking
 * is the short way.
 */
export function VoiceHint({ children }: { children: ReactNode }) {
  return (
    <p className="kiosk-voice-hint">
      <Microphone size={18} weight="fill" aria-hidden />
      {children}
    </p>
  );
}

/** The answers to the question Tanvi just asked, as a grid a thumb can cover. */
export function OptionGrid({ children }: { children: ReactNode }) {
  return <div className="kiosk-options">{children}</div>;
}

export function OptionChip({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`kiosk-chip${selected ? ' is-on' : ''}`}
      aria-pressed={selected}
      onClick={onClick}
    >
      <span>{label}</span>
      {selected ? <Check size={20} weight="bold" aria-hidden /> : null}
    </button>
  );
}

/**
 * Label/value pairs. Grouped under one soft rule rather than a hairline under
 * every row; spans, not divs, so a list can live inside a button.
 */
export function FactList({ rows }: { rows: ReadonlyArray<readonly [string, ReactNode]> }) {
  return (
    <span className="kiosk-facts">
      {rows.map(([label, value]) => (
        <span className="kiosk-fact" key={label}>
          <span className="kiosk-fact-label">{label}</span>
          <span className="kiosk-fact-value">{value}</span>
        </span>
      ))}
    </span>
  );
}

/**
 * The value being checked back, and the yes to it.
 *
 * The *full* display form, not the masked one: a customer confirming a number
 * has to see exactly what was heard. Correcting it is saying it again, which is
 * why the hint is there and a "no" button is not.
 */
export function ReadBack({
  language,
  value,
  onConfirm,
}: {
  language: Language;
  value: ConfirmValue;
  onConfirm: (field: string) => void;
}) {
  const copy = strings(language);
  return (
    <div className="kiosk-readback">
      <span className="kiosk-readback-label">{fieldLabel(value.field, language)}</span>
      <span className="kiosk-readback-value">{value.display}</span>
      <span className="kiosk-readback-prompt">{copy.confirmPrompt}</span>
      <TouchButton label={copy.confirmYes} onClick={() => onConfirm(value.field)} wide />
      <span className="kiosk-readback-hint">{copy.confirmHint}</span>
    </div>
  );
}

/** A tray's heading. Short, and only where the tray is a record rather than a choice. */
export function TrayTitle({ children }: { children: ReactNode }) {
  return <h2 className="kiosk-tray-title">{children}</h2>;
}

/** A state marker. `leaf` means eligible or confirmed, and nothing else. */
export function Tag({ children, tone = 'plain' }: { children: ReactNode; tone?: 'plain' | 'leaf' | 'accent' }) {
  return (
    <span className={`kiosk-tag is-${tone}`}>
      {tone === 'leaf' ? <CheckCircle size={16} weight="fill" aria-hidden /> : null}
      {children}
    </span>
  );
}

/**
 * The front of a card: its colourway, its name and the bank's mark. The face is
 * the one piece of artwork the page owns; every term printed beside it is still
 * a display string off the wire.
 */
export function CardFace({
  card,
  compact,
  small,
}: {
  card: Pick<CardView, 'id' | 'name'>;
  /** A thumbnail beside a line of text: the colourway alone. */
  compact?: boolean;
  /** A small face beside the card's name, which is then printed next to it. */
  small?: boolean;
}) {
  const [from, to] = CARD_FACE[card.id] ?? CARD_FACE_FALLBACK;
  return (
    <span
      className={`kiosk-face${compact ? ' is-compact' : ''}${small ? ' is-small' : ''}`}
      style={{ background: `linear-gradient(135deg, ${from} 0%, ${to} 100%)` }}
      aria-hidden
    >
      <span className="kiosk-face-bank">VANTAGE</span>
      <span className="kiosk-face-chip" />
      <span className="kiosk-face-name">{card.name}</span>
    </span>
  );
}

export function UiStyles() {
  return (
    <style>{`
      .kiosk-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        min-height: ${SIZE.touch}px;
        padding: 0 24px;
        border-radius: ${SIZE.radius}px;
        border: 1.5px solid transparent;
        font: inherit;
        font-size: ${SIZE.body}px;
        font-weight: 600;
        white-space: nowrap;
        cursor: pointer;
        transition: transform .14s cubic-bezier(0.16, 1, 0.3, 1), background .15s ease, border-color .15s ease;
      }
      .kiosk-btn.is-wide { width: 100%; }
      .kiosk-btn:active:not(:disabled) { transform: scale(0.98); }
      .kiosk-btn:focus-visible { outline: 3px solid ${FOCUS.ring}; outline-offset: 3px; }
      .kiosk-btn:disabled { opacity: .45; cursor: default; }
      .kiosk-btn.is-primary { background: ${COLOR.brand}; color: ${COLOR.surface}; }
      .kiosk-btn.is-primary:hover:not(:disabled) { background: #761823; }
      .kiosk-btn.is-quiet { background: transparent; color: ${COLOR.brand}; border-color: ${COLOR.rule}; }
      .kiosk-btn.is-quiet:hover:not(:disabled) { border-color: ${COLOR.brand}; }

      .kiosk-row { display: flex; gap: 10px; }
      .kiosk-row > .kiosk-btn { flex: 1 1 0; min-width: 0; }

      .kiosk-voice-hint {
        display: flex;
        align-items: center;
        gap: 8px;
        margin: 0 0 14px;
        font-size: 15px;
        font-weight: 500;
        color: ${COLOR.muted};
      }
      .kiosk-voice-hint svg { flex: none; color: ${COLOR.brand}; }

      .kiosk-options { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
      .kiosk-options > :last-child:nth-child(odd) { grid-column: 1 / -1; }
      .kiosk-chip {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        min-height: ${SIZE.touch}px;
        padding: 10px 16px;
        border-radius: ${SIZE.radius}px;
        border: 1.5px solid ${COLOR.rule};
        background: #FFFFFFF2;
        color: ${COLOR.ink};
        font: inherit;
        font-size: 17px;
        font-weight: 500;
        line-height: 1.25;
        text-align: left;
        cursor: pointer;
        transition: transform .14s cubic-bezier(0.16, 1, 0.3, 1), border-color .15s ease, background .15s ease;
      }
      .kiosk-chip:hover { border-color: rgba(142, 30, 42, 0.45); }
      .kiosk-chip:active { transform: scale(0.98); }
      .kiosk-chip:focus-visible { outline: 3px solid ${FOCUS.ring}; outline-offset: 2px; }
      .kiosk-chip svg { flex: none; color: ${COLOR.brand}; }
      .kiosk-chip.is-on {
        border-color: ${COLOR.accent};
        background: rgba(243, 115, 33, 0.14);
        font-weight: 600;
      }

      .kiosk-facts {
        display: grid;
        gap: 10px;
        padding-top: 12px;
        border-top: 1px solid ${COLOR.rule};
      }
      .kiosk-fact { display: grid; align-content: start; gap: 1px; }
      .kiosk-fact-label { font-size: 13px; font-weight: 500; color: ${COLOR.muted}; }
      .kiosk-fact-value { font-size: 16px; font-weight: 600; color: ${COLOR.ink}; line-height: 1.35; }

      .kiosk-readback {
        display: grid;
        gap: 4px;
        padding: 16px;
        margin-bottom: 14px;
        border-radius: ${SIZE.radius}px;
        border: 1.5px solid ${COLOR.accent};
        background: rgba(243, 115, 33, 0.08);
      }
      .kiosk-readback-label { font-size: 14px; font-weight: 500; color: ${COLOR.muted}; }
      .kiosk-readback-value { font-size: 28px; font-weight: 700; letter-spacing: 0.02em; }
      .kiosk-readback-prompt { margin-bottom: 10px; font-size: 16px; color: ${COLOR.muted}; }
      .kiosk-readback-hint { margin-top: 4px; font-size: 14px; color: ${COLOR.muted}; text-align: center; }

      .kiosk-tray-title {
        margin: 0 0 12px;
        font-size: ${SIZE.headline}px;
        font-weight: 700;
        line-height: 1.2;
        letter-spacing: -0.015em;
        color: ${COLOR.ink};
      }
      .kiosk-note { margin: 12px 0 0; font-size: 14px; color: ${COLOR.muted}; }

      .kiosk-tag {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 4px 10px;
        border-radius: ${SIZE.pill}px;
        font-size: 13px;
        font-weight: 600;
        white-space: nowrap;
      }
      .kiosk-tag.is-plain { background: rgba(30, 20, 22, 0.07); color: ${COLOR.muted}; }
      .kiosk-tag.is-leaf { background: rgba(31, 122, 92, 0.12); color: ${COLOR.leaf}; }
      .kiosk-tag.is-accent { background: ${COLOR.accent}; color: ${COLOR.brandDeep}; }

      /* A card front at ISO ID-1 proportions, so it reads as a card at a glance. */
      .kiosk-face {
        position: relative;
        display: block;
        width: 100%;
        aspect-ratio: 1.586;
        border-radius: 14px;
        overflow: hidden;
        color: #F5F7F4;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12), 0 12px 24px -14px rgba(78, 15, 23, 0.6);
      }
      .kiosk-face::after {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(115deg, rgba(255,255,255,0.16) 0%, rgba(255,255,255,0) 42%);
        pointer-events: none;
      }
      .kiosk-face-bank {
        position: absolute;
        top: 14px;
        left: 16px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.32em;
        opacity: .85;
      }
      .kiosk-face-chip {
        position: absolute;
        top: 40%;
        left: 16px;
        width: 34px;
        height: 25px;
        border-radius: 6px;
        background: linear-gradient(135deg, #E9C98B 0%, #B8914F 100%);
        opacity: .9;
      }
      .kiosk-face-name {
        position: absolute;
        left: 16px;
        right: 16px;
        bottom: 12px;
        font-size: 17px;
        font-weight: 600;
        letter-spacing: 0.01em;
      }
      .kiosk-face.is-small { width: 88px; flex: none; border-radius: 9px; }
      .kiosk-face.is-small .kiosk-face-name { display: none; }
      .kiosk-face.is-small .kiosk-face-bank { display: none; }
      .kiosk-face.is-small .kiosk-face-chip { width: 18px; height: 13px; left: 10px; border-radius: 3px; }
      .kiosk-face.is-compact { width: 84px; flex: none; border-radius: 9px; }
      .kiosk-face.is-compact .kiosk-face-bank,
      .kiosk-face.is-compact .kiosk-face-name { display: none; }
      .kiosk-face.is-compact .kiosk-face-chip { width: 16px; height: 12px; left: 9px; border-radius: 3px; }
    `}</style>
  );
}
