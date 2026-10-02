/**
 * The profile questions, one at a time, with their answers to tap.
 *
 * The heading is the bank's own short wording. The screen leads: the customer
 * taps an answer and the next question comes up. A customer who says it instead
 * has Tanvi tap it for them, and the screen moves the same way.
 *
 * **Correcting is picking again.** There is no "no, change it" button, because
 * the correction and the rejection are one gesture: tapping a different chip
 * while a value is being checked leaves as `ValueEdited` rather than
 * `ProfileAnswered`. The store decides which, off the ledger.
 */

import type { AskProfile, ConfirmValue } from '../actions.gen';
import { COPY } from '../copy';
import { OptionChip, OptionGrid, ReadBack, TrayTitle, VoiceHint } from '../ui';

export interface DiscoveryProps {
  question: AskProfile | null;
  checking: ConfirmValue | null;
  /** What the customer last tapped, per field — the chip stays lit meanwhile. */
  picked: Record<string, string>;
  onAnswer: (field: string, value: string) => void;
  onConfirm: (field: string) => void;
}

export function DiscoveryTray({
  question,
  checking,
  picked,
  onAnswer,
  onConfirm,
}: DiscoveryProps) {
  const copy = COPY;
  return (
    <div>
      {checking ? <ReadBack value={checking} onConfirm={onConfirm} /> : null}

      {question ? (
        <>
          <TrayTitle>{question.question}</TrayTitle>
          <VoiceHint>{copy.tapOrAsk}</VoiceHint>
          <OptionGrid>
            {question.options.map((option) => (
              <OptionChip
                key={option.value}
                label={option.label}
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
