/**
 * The one screen that takes characters rather than a choice.
 *
 * A mobile number and a PAN are the two things a customer cannot answer with a
 * chip, and until now they could only be spoken. `AskValue` puts the same
 * question on the glass: one labelled field, the on-screen form of what has been
 * typed so far, and a submit. Typing and pressing Enter is the whole
 * interaction — the field takes focus when the screen arrives, so a customer
 * with a keyboard and no pointer never has to reach for one.
 *
 * **The value leaves as `ValueEntered` and comes back as `ConfirmValue`.** The
 * screen does not settle anything itself: the brain normalises what was typed,
 * decides it is a value, and dispatches the confirmation that puts it in the
 * ledger. So there is no validation here beyond refusing to send nothing —
 * a shape rule written on this screen would be a second copy of one that
 * already lives in Python, and the two would part company.
 *
 * `kind` steers the keyboard, nothing else: `tel` asks for a number pad, `text`
 * for characters in capitals.
 *
 * The voice is live the whole time this screen is up, so a customer who would
 * rather say the number still can. That arrives as Rohan checking a value back,
 * which is why the read-back and its yes render here too — the same pair
 * discovery uses, because it is the same moment.
 */

import { useState, type FormEvent } from 'react';
import { COLOR, FOCUS, SIZE } from '../brand';
import type { AskValue, ConfirmValue } from '../actions.gen';
import { fieldLabel, strings, type Language } from '../language';
import { ConfirmControl, HeardValue, Ledger, StageTitle } from '../ui';

/**
 * What the totem shows of a value it is still being handed — the mirror of the
 * brain's `masked_form`, run over a half-typed string so the customer can see
 * the masking before they commit to it rather than after.
 */
function maskedPreview(kind: string, raw: string): string {
  if (kind === 'tel') {
    const digits = raw.replace(/\D/g, '');
    const head = 'X'.repeat(Math.min(5, digits.length));
    const tail = digits.slice(5);
    return tail ? `${head} ${tail}` : head;
  }
  const characters = raw.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
  return [...characters].map((char, at) => (at >= 5 && at <= 8 ? 'X' : char)).join('');
}

/** The record: what is being asked for, what is being checked, what has settled. */
export function ValueEntryStage({
  language,
  entry,
  checking,
  ledger,
}: {
  language: Language;
  entry: AskValue | null;
  checking: ConfirmValue | null;
  ledger: readonly ConfirmValue[];
}) {
  const copy = strings(language);
  if (!entry) return null;
  return (
    <div className="kiosk-value">
      <StageTitle>{entry.label}</StageTitle>
      <p className="kiosk-value-hint">{copy.valueHint}</p>

      {checking ? <HeardValue language={language} value={checking} /> : null}

      <Ledger language={language} entries={ledger} />

      <style>{`
        .kiosk-value { display: flex; flex-direction: column; gap: 16px; }
        .kiosk-value-hint { margin: 0; font-size: 17px; color: ${COLOR.muted}; }
      `}</style>
    </div>
  );
}

/**
 * The field itself, in the band a hand reaches.
 *
 * It is a real `<form>`: Enter submits it because that is what a form with a
 * submit button does, not because a key handler was added to make it look that
 * way. The parent re-keys this component per field, so moving from mobile to
 * PAN arrives as a fresh, empty, focused input.
 */
export function ValueEntryControls({
  language,
  entry,
  checking,
  onEnter,
  onConfirm,
}: {
  language: Language;
  entry: AskValue | null;
  checking: ConfirmValue | null;
  onEnter: (field: string, value: string) => void;
  onConfirm: (field: string) => void;
}) {
  const copy = strings(language);
  const [draft, setDraft] = useState('');
  if (!entry) return null;

  const characters = entry.kind !== 'tel';
  const typed = draft.trim();

  const submit = (moment: FormEvent) => {
    moment.preventDefault();
    if (typed) onEnter(entry.field, typed);
  };

  return (
    <>
      {checking ? (
        <ConfirmControl language={language} field={checking.field} onConfirm={onConfirm} />
      ) : null}
      <form className="kiosk-value-form" onSubmit={submit}>
        <label className="kiosk-value-label" htmlFor="kiosk-value-input">
          {fieldLabel(entry.field, language)}
        </label>
        <div className="kiosk-value-line">
          <input
            id="kiosk-value-input"
            className="kiosk-value-input"
            value={draft}
            onChange={(moment) => setDraft(moment.target.value)}
            inputMode={characters ? 'text' : 'numeric'}
            autoCapitalize={characters ? 'characters' : 'off'}
            autoComplete="off"
            spellCheck={false}
            aria-describedby="kiosk-value-mask"
            // The screen this lives on is the only thing on it; a customer who
            // arrives here by keyboard should be typing, not hunting for the field.
            autoFocus
          />
          <button type="submit" className="kiosk-btn is-primary" disabled={!typed}>
            {copy.valueSubmit}
          </button>
        </div>
        <p className="kiosk-value-mask" id="kiosk-value-mask">
          <span className="kiosk-value-mask-label">{copy.valueMasked}</span>
          <span className="kiosk-value-mask-value">{maskedPreview(entry.kind, draft) || '—'}</span>
        </p>

        <style>{`
          .kiosk-value-form {
            flex-basis: 100%;
            display: flex;
            flex-direction: column;
            gap: 8px;
          }
          .kiosk-value-label {
            font-size: 15px;
            font-weight: 700;
            letter-spacing: .02em;
            text-transform: uppercase;
            color: ${COLOR.muted};
          }
          .kiosk-value-line { display: flex; gap: 12px; align-items: stretch; }
          .kiosk-value-input {
            flex: 1 1 auto;
            min-width: 0;
            min-height: ${SIZE.touch}px;
            padding: 0 18px;
            border-radius: 14px;
            border: 2px solid ${COLOR.rule};
            background: #FFFFFF;
            color: ${COLOR.ink};
            font: inherit;
            font-size: ${SIZE.headline}px;
            font-weight: 700;
            letter-spacing: .06em;
            ${characters ? 'text-transform: uppercase;' : ''}
          }
          .kiosk-value-input:focus-visible {
            outline: 3px solid ${FOCUS.ring};
            outline-offset: 2px;
            border-color: ${COLOR.amber};
          }
          .kiosk-value-mask {
            display: flex;
            align-items: baseline;
            gap: 10px;
            margin: 0;
          }
          .kiosk-value-mask-label {
            font-size: 15px;
            font-weight: 700;
            letter-spacing: .02em;
            text-transform: uppercase;
            color: ${COLOR.muted};
          }
          .kiosk-value-mask-value {
            font-size: 17px;
            font-weight: 700;
            letter-spacing: .08em;
            color: ${COLOR.ink};
          }
        `}</style>
      </form>
    </>
  );
}
