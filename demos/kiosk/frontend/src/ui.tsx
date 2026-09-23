/**
 * The kiosk's touch primitives.
 *
 * Every size in here is a standing-up-at-a-totem size: 64px is the floor for
 * anything a finger lands on, 20px the floor for anything read from a metre
 * away. Nothing shrinks below that on a phone — the layout gives up columns
 * first.
 *
 * The rules live in one {@link UiStyles} block that the totem renders once, so
 * the primitives themselves stay style-object-and-class thin.
 */

import type { ReactNode } from 'react';
import type { ConfirmValue } from './actions.gen';
import { COLOR, FOCUS, SIZE } from './brand';
import { fieldLabel, strings, type Language } from './language';

/** A control in the lower band. `quiet` is the one that is always there. */
export function TouchButton({
  label,
  onClick,
  tone = 'primary',
  disabled,
}: {
  label: string;
  onClick: () => void;
  tone?: 'primary' | 'quiet';
  disabled?: boolean;
}) {
  return (
    <button type="button" className={`kiosk-btn is-${tone}`} onClick={onClick} disabled={disabled}>
      {label}
    </button>
  );
}

/** One answer to the question on the stage. */
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
      {label}
    </button>
  );
}

/**
 * A label/value pair — the ledger, and the cards' comparison rows.
 *
 * Spans, not divs: these rows render inside the shortlist's row `<button>`, and
 * a button may only contain phrasing content. The layout comes from the class.
 */
export function FactRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <span className="kiosk-fact">
      <span className="kiosk-fact-label">{label}</span>
      <span className="kiosk-fact-value">{value}</span>
    </span>
  );
}

/**
 * The value being checked back, while it is being checked.
 *
 * The *full* display form, not the masked one: a customer confirming a number
 * has to see exactly what was heard. The masked form is for afterwards, in the
 * ledger, where a PAN has no business standing on a screen in a branch.
 */
export function HeardValue({ language, value }: { language: Language; value: ConfirmValue }) {
  const copy = strings(language);
  return (
    <div className="kiosk-heard">
      <span className="kiosk-heard-label">{fieldLabel(value.field, language)}</span>
      <span className="kiosk-heard-value">{value.display}</span>
      <span className="kiosk-heard-prompt">{copy.confirmPrompt}</span>
    </div>
  );
}

/**
 * The yes to a read-back, and the line telling the customer they may simply say
 * it again instead. It rides in the lower band of whichever screen is up, since
 * Rohan can check a value back at any point he heard one.
 */
export function ConfirmControl({
  language,
  field,
  onConfirm,
}: {
  language: Language;
  field: string;
  onConfirm: (field: string) => void;
}) {
  const copy = strings(language);
  return (
    <div className="kiosk-confirm">
      <TouchButton label={copy.confirmYes} onClick={() => onConfirm(field)} />
      <span className="kiosk-confirm-hint">{copy.confirmHint}</span>
    </div>
  );
}

/**
 * What has settled so far, masked. Two screens show it — the questions and the
 * typed values — and it is one component so that the record a customer has been
 * watching does not change shape halfway through the journey.
 */
export function Ledger({
  language,
  entries,
}: {
  language: Language;
  entries: readonly ConfirmValue[];
}) {
  if (entries.length === 0) return null;
  return (
    <section className="kiosk-ledger">
      <h3 className="kiosk-ledger-title">{strings(language).ledgerTitle}</h3>
      {entries.map((entry) => (
        <FactRow
          key={entry.field}
          label={fieldLabel(entry.field, language)}
          value={<Tag tone="leaf">{entry.masked}</Tag>}
        />
      ))}
    </section>
  );
}

/** The stage's heading. One per screen, and never more. */
export function StageTitle({ children }: { children: ReactNode }) {
  return <h2 className="kiosk-stage-title">{children}</h2>;
}

/**
 * A state marker. `leaf` is reserved: it means eligible or confirmed, and it
 * means nothing else anywhere in this demo.
 */
export function Tag({ children, tone = 'plain' }: { children: ReactNode; tone?: 'plain' | 'leaf' }) {
  return <span className={`kiosk-tag is-${tone}`}>{children}</span>;
}

export function UiStyles() {
  return (
    <style>{`
      .kiosk-btn {
        min-height: ${SIZE.touch}px;
        padding: 0 28px;
        border-radius: 14px;
        border: 2px solid transparent;
        font: inherit;
        font-size: ${SIZE.body}px;
        font-weight: 700;
        cursor: pointer;
        transition: transform .12s ease, background .15s ease, border-color .15s ease;
      }
      .kiosk-btn:active:not(:disabled) { transform: translateY(1px); }
      .kiosk-btn:focus-visible { outline: 3px solid ${FOCUS.ring}; outline-offset: 3px; }
      .kiosk-btn:disabled { opacity: .45; cursor: default; }
      .kiosk-btn.is-primary { background: ${COLOR.amber}; color: ${COLOR.umber}; }
      .kiosk-btn.is-primary:hover:not(:disabled) { background: #D97A08; }
      .kiosk-btn.is-quiet {
        background: transparent;
        color: ${COLOR.muted};
        border-color: ${COLOR.rule};
      }
      .kiosk-btn.is-quiet:hover:not(:disabled) { border-color: ${COLOR.amber}; color: ${COLOR.ink}; }

      .kiosk-chip {
        min-height: ${SIZE.touch}px;
        padding: 0 22px;
        border-radius: 14px;
        border: 2px solid ${COLOR.rule};
        background: #FFFFFF;
        color: ${COLOR.ink};
        font: inherit;
        font-size: ${SIZE.body}px;
        font-weight: 600;
        cursor: pointer;
        transition: border-color .15s ease, background .15s ease;
      }
      .kiosk-chip:hover { border-color: ${COLOR.amber}; }
      .kiosk-chip:focus-visible { outline: 3px solid ${FOCUS.ring}; outline-offset: 3px; }
      .kiosk-chip.is-on {
        border-color: ${COLOR.amber};
        background: rgba(232, 133, 11, 0.14);
        font-weight: 700;
      }

      .kiosk-fact {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 18px;
        padding: 10px 0;
        border-bottom: 1px solid ${COLOR.rule};
      }
      .kiosk-fact:last-child { border-bottom: 0; }
      .kiosk-fact-label {
        flex: none;
        font-size: 16px;
        font-weight: 600;
        letter-spacing: .02em;
        text-transform: uppercase;
        color: ${COLOR.muted};
      }
      .kiosk-fact-value {
        text-align: right;
        font-size: ${SIZE.body}px;
        font-weight: 600;
        color: ${COLOR.ink};
      }

      .kiosk-heard {
        display: flex;
        flex-direction: column;
        gap: 2px;
        padding: 14px 18px;
        border-radius: 14px;
        border: 2px solid ${COLOR.amber};
        background: rgba(232, 133, 11, 0.09);
      }
      .kiosk-heard-label {
        font-size: 15px;
        font-weight: 700;
        letter-spacing: .02em;
        text-transform: uppercase;
        color: ${COLOR.muted};
      }
      .kiosk-heard-value { font-size: ${SIZE.headline}px; font-weight: 800; }
      .kiosk-heard-prompt { font-size: 17px; color: ${COLOR.muted}; }

      .kiosk-confirm {
        display: flex;
        align-items: center;
        gap: 14px;
        flex-basis: 100%;
      }
      .kiosk-confirm-hint { font-size: 16px; color: ${COLOR.muted}; }

      .kiosk-ledger-title {
        margin: 0 0 4px;
        font-size: 15px;
        font-weight: 700;
        letter-spacing: .04em;
        text-transform: uppercase;
        color: ${COLOR.muted};
      }

      .kiosk-stage-title {
        margin: 0 0 14px;
        font-size: ${SIZE.headline}px;
        font-weight: 800;
        line-height: 1.2;
        color: ${COLOR.ink};
      }

      .kiosk-tag {
        display: inline-flex;
        align-items: center;
        padding: 5px 12px;
        border-radius: 999px;
        font-size: 15px;
        font-weight: 700;
        letter-spacing: .01em;
      }
      .kiosk-tag.is-plain { background: rgba(23, 19, 16, 0.07); color: ${COLOR.muted}; }
      .kiosk-tag.is-leaf { background: rgba(31, 122, 92, 0.14); color: ${COLOR.leaf}; }
    `}</style>
  );
}
