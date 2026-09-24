/**
 * The four questions — as answers, not as questions.
 *
 * Tess asks each one aloud, and the tray carries the same question as its
 * heading — the bank's own short wording, not hers — so a customer who missed
 * a word can still read what is being asked. The answers sit under it, below a
 * line that says speaking is the short way.
 *
 * **Correcting is picking again.** There is no "no, change it" button, because
 * the correction and the rejection are one gesture: tapping a different chip
 * while a value is being checked leaves as `ValueEdited` rather than
 * `ProfileAnswered`. The store decides which, off the ledger.
 */

import type { AskProfile, ConfirmValue } from '../actions.gen';
import { strings, type Language } from '../language';
import { OptionChip, OptionGrid, ReadBack, TrayTitle, VoiceHint } from '../ui';

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
          <TrayTitle>{question.question}</TrayTitle>
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
