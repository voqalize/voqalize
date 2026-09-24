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
 * Speaking it is the first way. That arrives as Tanvi checking a value back,
 * which is why the read-back and its yes render here too — the same block
 * discovery uses, because it is the same moment.
 */

import { useState, type FormEvent } from 'react';
import { COLOR, FOCUS, SIZE } from '../brand';
import type { AskValue, ConfirmValue } from '../actions.gen';
import { fieldLabel, strings, type Language } from '../language';
import { ReadBack, TrayTitle, VoiceHint } from '../ui';

/** A mouse or trackpad, which on this page means a keyboard is to hand too. */
const FINE_POINTER = typeof window !== 'undefined' && window.matchMedia('(pointer: fine)').matches;

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

/**
 * The field, and the read-back of what was heard, in the tray a hand reaches.
 *
 * It is a real `<form>`: Enter submits it because that is what a form with a
 * submit button does, not because a key handler was added to make it look that
 * way. The parent re-keys this component per field, so moving from mobile to
 * PAN arrives as a fresh, empty input.
 */
export function ValueEntryTray({
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
  const preview = maskedPreview(entry.kind, draft);

  const submit = (moment: FormEvent) => {
    moment.preventDefault();
    if (typed) onEnter(entry.field, typed);
  };

  return (
    <div>
      {checking ? <ReadBack language={language} value={checking} onConfirm={onConfirm} /> : null}
      <TrayTitle>{entry.label}</TrayTitle>
      <VoiceHint>{copy.valueHint}</VoiceHint>
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
            autoFocus={FINE_POINTER}
          />
          <button type="submit" className="kiosk-btn is-primary" disabled={!typed}>
            {copy.valueSubmit}
          </button>
        </div>
        <p className="kiosk-value-mask" id="kiosk-value-mask">
          <span>{copy.valueMasked}</span>
          <span className="kiosk-value-mask-value">{preview}</span>
        </p>

        <style>{`
          .kiosk-value-form { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
          .kiosk-value-label { font-size: 14px; font-weight: 500; color: ${COLOR.muted}; }
          .kiosk-value-line { display: flex; gap: 10px; align-items: stretch; }
          .kiosk-value-input {
            flex: 1 1 auto;
            min-width: 0;
            min-height: ${SIZE.touch}px;
            padding: 0 16px;
            border-radius: ${SIZE.radius}px;
            border: 1.5px solid ${COLOR.rule};
            background: #FFFFFF;
            color: ${COLOR.ink};
            font: inherit;
            font-size: 22px;
            font-weight: 600;
            letter-spacing: .06em;
            ${characters ? 'text-transform: uppercase;' : ''}
          }
          .kiosk-value-input:focus-visible { outline: 3px solid ${FOCUS.ring}; outline-offset: 2px; border-color: ${COLOR.brand}; }
          .kiosk-value-mask { display: flex; align-items: baseline; gap: 10px; min-height: 22px; margin: 0; font-size: 14px; color: ${COLOR.muted}; }
          .kiosk-value-mask-value { font-size: 16px; font-weight: 600; letter-spacing: .08em; color: ${COLOR.ink}; }
        `}</style>
      </form>
    </div>
  );
}
