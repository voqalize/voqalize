/**
 * The four questions — as answers, not as questions.
 *
 * Tess asks each one aloud, so the tray does not print it: a question on the
 * glass is the same sentence twice, and it pushes the answers down out of reach.
 * What the tray holds is what a hand can do instead of answering — the choices,
 * under a line that says speaking is the short way.
 *
 * **Correcting is picking again.** There is no "no, change it" button, because
 * the correction and the rejection are one gesture: tapping a different chip
 * while a value is being checked leaves as `ValueEdited` rather than
 * `ProfileAnswered`. The store decides which, off the ledger.
 */

import type { AskProfile, ConfirmValue } from '../actions.gen';
import { strings, type Language } from '../language';
import { OptionChip, OptionGrid, ReadBack, VoiceHint } from '../ui';

export interface DiscoveryProps {
  language: Language;
  question: AskProfile | null;
  checking: ConfirmValue | null;
  /** What the customer last tapped, per field — the chip stays lit meanwhile. */
  picked: Record<string, string>;
  onAnswer: (field: string, value: string) => void;
  onConfirm: (field: string) => void;
}

export function DiscoveryTray({
  language,
  question,
  checking,
  picked,
  onAnswer,
  onConfirm,
}: DiscoveryProps) {
  const copy = strings(language);
  return (
    <div>
      {checking ? <ReadBack language={language} value={checking} onConfirm={onConfirm} /> : null}

      {question ? (
        <>
          <VoiceHint>{copy.sayOrTap}</VoiceHint>
          <OptionGrid>
            {question.options.map((option) => (
              <OptionChip
                key={option.value}
                label={language === 'hi' ? option.label_hi : option.label}
                selected={picked[question.field] === option.value}
                onClick={() => onAnswer(question.field, option.value)}
              />
            ))}
          </OptionGrid>
        </>
      ) : null}

    </div>
  );
}
