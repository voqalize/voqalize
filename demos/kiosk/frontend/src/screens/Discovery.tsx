/**
 * Discovery — the four questions, and the ledger of what has been settled.
 *
 * The stage carries the record: the question, the value Rohan is checking back,
 * and everything already agreed. The lower band carries the two things a finger
 * can do — say yes to a value in flight, and pick an answer.
 *
 * **Correcting is picking again.** There is no "no, change it" button, because
 * the correction and the rejection are one gesture: tapping a different chip
 * while a value is being checked leaves as `ValueEdited` rather than
 * `ProfileAnswered`. The store decides which, off the ledger.
 *
 * The confirmed row shows the *masked* form. While a value is being checked the
 * customer needs to see exactly what was heard, so that row shows the full
 * `display` — but a settled PAN has no business standing on a screen afterwards.
 */

import type { AskProfile, ConfirmValue } from '../actions.gen';
import type { Language } from '../language';
import { ConfirmControl, HeardValue, Ledger, OptionChip, StageTitle } from '../ui';

export interface DiscoveryProps {
  language: Language;
  question: AskProfile | null;
  checking: ConfirmValue | null;
  ledger: readonly ConfirmValue[];
}

export function DiscoveryStage({ language, question, checking, ledger }: DiscoveryProps) {
  return (
    <div className="kiosk-discovery">
      {question ? <StageTitle>{question.question}</StageTitle> : null}

      {checking ? <HeardValue language={language} value={checking} /> : null}

      <Ledger language={language} entries={ledger} />

      <style>{`
        .kiosk-discovery { display: flex; flex-direction: column; gap: 16px; }
      `}</style>
    </div>
  );
}

export interface DiscoveryControlsProps {
  language: Language;
  question: AskProfile | null;
  checking: ConfirmValue | null;
  /** What the customer last tapped, per field — the chip stays lit meanwhile. */
  picked: Record<string, string>;
  onAnswer: (field: string, value: string) => void;
  onConfirm: (field: string) => void;
}

export function DiscoveryControls({
  language,
  question,
  checking,
  picked,
  onAnswer,
  onConfirm,
}: DiscoveryControlsProps) {
  return (
    <>
      {checking ? (
        <ConfirmControl language={language} field={checking.field} onConfirm={onConfirm} />
      ) : null}

      {question
        ? question.options.map((option) => (
            <OptionChip
              key={option.value}
              label={language === 'hi' ? option.label_hi : option.label}
              selected={picked[question.field] === option.value}
              onClick={() => onAnswer(question.field, option.value)}
            />
          ))
        : null}
    </>
  );
}
