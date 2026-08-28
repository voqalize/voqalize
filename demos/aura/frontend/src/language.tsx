/**
 * The language the caller picks before the call exists.
 *
 * Aura is an Indian retail bank, so the language is a property of the *call*,
 * chosen the way a caller picks a queue on an IVR — and it is settled here,
 * before anything connects, rather than switched mid-sentence. The name rides
 * the connect request in `init`; the brain reads it once in `on_session_start`
 * and moves all three things that have to move together (the recognizer, the
 * reference clip, and the prompt). See `backend/brain.py` → the Language
 * section: that file is the authority, and this list is its page-side mirror.
 *
 * **Ten, and exactly ten.** OmniVoice has voice-cloning reference clips for
 * these; `vql-stt` understands more, but naming a language TTS cannot speak is
 * refused at the call site rather than quietly served with the English clip. So
 * the page offers what can actually be spoken back.
 *
 * Only the *voice* moves. Every article, video and button on screen stays in
 * English — the customer is reading Aura's real English help pages while Aria
 * describes them in their own language, which is what an L1 support call
 * actually is.
 */

/** A language name, spelled exactly as the brain's `LanguageName` spells it. */
export type LanguageName = (typeof LANGUAGES)[number]['name'];

/**
 * The offer, in the order a customer scans it: English first because it is the
 * default and the fallback, then the rest by number of speakers.
 *
 * `native` is what the chip reads, because a Tamil speaker looking for their
 * language looks for தமிழ் and not for the word "Tamil"; `name` is what goes on
 * the wire, because the brain's table is keyed in English and a wire value is
 * not a label.
 */
export const LANGUAGES = [
  { name: 'English', native: 'English' },
  { name: 'Hindi', native: 'हिन्दी' },
  { name: 'Bengali', native: 'বাংলা' },
  { name: 'Marathi', native: 'मराठी' },
  { name: 'Telugu', native: 'తెలుగు' },
  { name: 'Tamil', native: 'தமிழ்' },
  { name: 'Gujarati', native: 'ગુજરાતી' },
  { name: 'Kannada', native: 'ಕನ್ನಡ' },
  { name: 'Malayalam', native: 'മലയാളം' },
  { name: 'Punjabi', native: 'ਪੰਜਾਬੀ' },
] as const;

/** What an unpicked call speaks — and what the brain falls back to. */
export const DEFAULT_LANGUAGE: LanguageName = 'English';

/**
 * The picker, for `DemoGate`'s slot.
 *
 * Styled entirely out of the gate's own custom properties (`--vq-fill`,
 * `--vq-fg`, `--vq-line`, …), which it publishes on the overlay for exactly
 * this: the chips pick up the panel's theme and Aura's indigo without this file
 * knowing either one.
 */
export function LanguagePicker({
  value,
  onChange,
}: {
  value: LanguageName;
  onChange: (language: LanguageName) => void;
}) {
  return (
    <fieldset className="aura-lang">
      <legend>Language for this call</legend>
      <div className="aura-lang-row">
        {LANGUAGES.map((lang) => (
          <button
            key={lang.name}
            type="button"
            className={`aura-lang-chip${lang.name === value ? ' is-on' : ''}`}
            aria-pressed={lang.name === value}
            onClick={() => onChange(lang.name)}
          >
            {lang.native}
          </button>
        ))}
      </div>
      <p className="aura-lang-note">Aria speaks your language; the help centre stays in English.</p>
      <style>{`
        .aura-lang { border: 0; margin: 0; padding: 0; min-width: 0; }
        .aura-lang legend {
          padding: 0;
          font-size: 12px;
          font-weight: 700;
          letter-spacing: .04em;
          text-transform: uppercase;
          color: var(--vq-faint, #7E96BE);
        }
        .aura-lang-row {
          display: flex;
          flex-wrap: wrap;
          gap: 7px;
          margin-top: 10px;
        }
        .aura-lang-chip {
          font: inherit;
          font-size: 13px;
          line-height: 1;
          padding: 8px 12px;
          border-radius: 999px;
          border: 1px solid var(--vq-line, rgba(120,165,240,.18));
          background: transparent;
          color: var(--vq-soft, #A8BDDF);
          cursor: pointer;
          transition: border-color .15s ease, color .15s ease, background .15s ease;
        }
        .aura-lang-chip:hover { border-color: var(--vq-link, #8B5CF6); color: var(--vq-fg, #EAF1FD); }
        .aura-lang-chip:focus-visible { outline: 2px solid var(--vq-link, #8B5CF6); outline-offset: 2px; }
        .aura-lang-chip.is-on {
          background: var(--vq-fill, #4F46E5);
          border-color: var(--vq-fill, #4F46E5);
          color: var(--vq-on-fill, #fff);
          font-weight: 650;
        }
        .aura-lang-note {
          margin: 10px 0 0;
          font-size: 12.5px;
          line-height: 1.5;
          color: var(--vq-faint, #7E96BE);
        }
      `}</style>
    </fieldset>
  );
}
