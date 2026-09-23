/**
 * The script the totem is set in, and the chip that switches it.
 *
 * Two languages, because a Vantage branch serves both and a customer who reads
 * Devanagari should not have to read a shortlist in Latin. Rohan speaks both and
 * can switch mid-call.
 *
 * **The chip moves the screen only.** Moving the *voice* means moving the STT
 * and TTS legs together in one `session.configure(...)`, and that is the brain's
 * to do — a page that set one leg would be the half-applied-pair bug, which is
 * silent: the words stay right and only the speaker is wrong. So a customer who
 * wants Rohan in Hindi asks him, and he moves both legs and the prompt at once.
 * The chip is for the reader, and the label under it says so.
 */

import { useCallback } from 'react';
import { COLOR, FOCUS, FONT, SIZE } from './brand';

export type Language = 'en' | 'hi';

/** Each language named in its own script, which is how a reader finds theirs. */
export const LANGUAGE_LABEL: Record<Language, string> = {
  en: 'English',
  hi: 'हिन्दी',
};

/** The face the totem sets its text in. */
export function fontFor(language: Language): string {
  return language === 'hi' ? FONT.hi : FONT.en;
}

/**
 * Every fixed string on the totem. The variable ones — the question, the
 * reasons, the taglines, the consent bullets — arrive from the brain already in
 * the call's language, so they are not here.
 */
interface Strings {
  assistant: string;
  assistantRole: string;
  attractTitle: string;
  attractBody: string;
  attractCue: string;
  attractBegin: string;
  ledgerTitle: string;
  confirmPrompt: string;
  confirmYes: string;
  confirmHint: string;
  eligibilityTitle: string;
  eligibilityNext: string;
  lineLabel: string;
  bankerConfirms: string;
  shortlistTitle: string;
  bestForYou: string;
  likelyEligible: string;
  compareAll: string;
  chooseCard: string;
  tapToExpand: string;
  rowFee: string;
  rowWaiver: string;
  rowReward: string;
  rowHero: string;
  detailNeeds: string;
  detailBack: string;
  consentTitle: string;
  consentAgree: string;
  valueHint: string;
  valueMasked: string;
  valueSubmit: string;
  handoffTitle: string;
  restart: string;
  screenOnly: string;
}

const EN: Strings = {
  assistant: 'Rohan',
  assistantRole: 'AI assistant',
  attractTitle: 'Find the right Vantage card',
  attractBody: 'Four questions, out loud. Rohan ranks three cards for you and prints a code for the desk.',
  attractCue: 'Say hello, or press Begin',
  attractBegin: 'Begin',
  ledgerTitle: 'What Rohan has so far',
  confirmPrompt: 'Did I get that right?',
  confirmYes: 'Yes, that’s right',
  confirmHint: 'Not quite? Just say it again.',
  eligibilityTitle: 'Where you stand',
  eligibilityNext: 'Show me the cards',
  lineLabel: 'Indicative limit',
  bankerConfirms: 'A banker will confirm this at the desk.',
  shortlistTitle: 'Three cards for you',
  bestForYou: 'Best for you',
  likelyEligible: 'Likely eligible',
  compareAll: 'Compare all three',
  chooseCard: 'Choose this card',
  tapToExpand: 'Tap a card to open it',
  rowFee: 'Annual fee',
  rowWaiver: 'Fee waiver',
  rowReward: 'Rewards',
  rowHero: 'Stand-out',
  detailNeeds: 'What it asks for',
  detailBack: 'Back to the three',
  consentTitle: 'Before we hand you over',
  consentAgree: 'I agree',
  valueHint: 'Type it and press Enter, or just say it.',
  valueMasked: 'On screen as',
  valueSubmit: 'Continue',
  handoffTitle: 'Show this at the desk',
  restart: 'Start over',
  screenOnly: 'Changes the screen. Ask Rohan to change his voice.',
};

const HI: Strings = {
  assistant: 'रोहन',
  assistantRole: 'एआई सहायक',
  attractTitle: 'अपने लिए सही वैंटेज कार्ड चुनिए',
  attractBody: 'चार सवाल, बोलकर। रोहन आपके लिए तीन कार्ड चुनेगा और डेस्क के लिए एक कोड देगा।',
  attractCue: 'नमस्ते कहिए, या शुरू करें दबाइए',
  attractBegin: 'शुरू करें',
  ledgerTitle: 'रोहन के पास अब तक',
  confirmPrompt: 'क्या मैंने सही सुना?',
  confirmYes: 'हाँ, सही है',
  confirmHint: 'सही नहीं? बस फिर से बोलिए।',
  eligibilityTitle: 'आपकी स्थिति',
  eligibilityNext: 'कार्ड दिखाइए',
  lineLabel: 'संकेतात्मक सीमा',
  bankerConfirms: 'डेस्क पर एक बैंकर इसकी पुष्टि करेगा।',
  shortlistTitle: 'आपके लिए तीन कार्ड',
  bestForYou: 'आपके लिए सर्वोत्तम',
  likelyEligible: 'संभावित रूप से पात्र',
  compareAll: 'तीनों की तुलना करें',
  chooseCard: 'यह कार्ड चुनें',
  tapToExpand: 'खोलने के लिए कार्ड पर टैप कीजिए',
  rowFee: 'वार्षिक शुल्क',
  rowWaiver: 'शुल्क माफी',
  rowReward: 'रिवॉर्ड',
  rowHero: 'खास बात',
  detailNeeds: 'क्या चाहिए',
  detailBack: 'तीनों पर वापस',
  consentTitle: 'आगे बढ़ने से पहले',
  consentAgree: 'मैं सहमत हूँ',
  valueHint: 'टाइप करके एंटर दबाइए, या बोलिए।',
  valueMasked: 'स्क्रीन पर',
  valueSubmit: 'आगे बढ़ें',
  handoffTitle: 'डेस्क पर यह दिखाइए',
  restart: 'फिर से शुरू करें',
  screenOnly: 'यह केवल स्क्रीन बदलता है। आवाज़ बदलने के लिए रोहन से कहिए।',
};

export function strings(language: Language): Strings {
  return language === 'hi' ? HI : EN;
}

/**
 * What the eligibility chip calls each band.
 *
 * `band` arrives as a wire token (`wide`, `standard`, `secured`) and a wire token
 * is not a label. A band this build does not know is printed as it came rather
 * than dropped: an unexplained word on screen beats a missing verdict, and the
 * reasons beside it carry the meaning either way.
 */
const BAND_LABEL: Record<string, { en: string; hi: string }> = {
  wide: { en: 'Our full range', hi: 'हमारी पूरी श्रेणी' },
  standard: { en: 'Our standard range', hi: 'हमारी सामान्य श्रेणी' },
  secured: { en: 'Secured card', hi: 'सुरक्षित कार्ड' },
};

export function bandLabel(band: string, language: Language): string {
  const known = BAND_LABEL[band];
  if (!known) return band;
  return language === 'hi' ? known.hi : known.en;
}

/**
 * What the ledger calls each field. A field this build does not know is printed
 * from its wire name, readably — the screen can afford that, the voice cannot.
 */
const FIELD_LABEL: Record<string, { en: string; hi: string }> = {
  employment: { en: 'Employment', hi: 'रोज़गार' },
  income_band: { en: 'Monthly income', hi: 'मासिक आय' },
  existing_cards: { en: 'Cards you hold', hi: 'मौजूदा कार्ड' },
  spend_category: { en: 'Where you spend most', hi: 'सबसे ज़्यादा खर्च' },
  mobile: { en: 'Mobile', hi: 'मोबाइल' },
  pan: { en: 'PAN', hi: 'पैन' },
};

export function fieldLabel(field: string, language: Language): string {
  const known = FIELD_LABEL[field];
  if (known) return language === 'hi' ? known.hi : known.en;
  const words = field.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * The chip in the brand bar — the one touchable thing in the upper band, and
 * small enough to stay out of the way of Rohan.
 */
export function LanguageChip({
  value,
  onChange,
}: {
  value: Language;
  onChange: (language: Language) => void;
}) {
  const toggle = useCallback(() => onChange(value === 'en' ? 'hi' : 'en'), [value, onChange]);
  return (
    <>
      <button
        type="button"
        className="kiosk-lang"
        onClick={toggle}
        aria-label={`Screen language: ${LANGUAGE_LABEL[value]}. Tap to switch.`}
        title={strings(value).screenOnly}
      >
        {(['en', 'hi'] as const).map((code) => (
          <span
            key={code}
            className={`kiosk-lang-half${code === value ? ' is-on' : ''}`}
            style={{ fontFamily: fontFor(code) }}
          >
            {LANGUAGE_LABEL[code]}
          </span>
        ))}
      </button>
      <style>{`
        .kiosk-lang {
          display: flex;
          align-items: stretch;
          gap: 2px;
          padding: 3px;
          min-height: 48px;
          border-radius: 999px;
          border: 1px solid rgba(251, 247, 242, 0.28);
          background: rgba(251, 247, 242, 0.08);
          cursor: pointer;
          font: inherit;
        }
        /* Amber here: this chip sits on the umber bar, where the paper ring would vanish. */
        .kiosk-lang:focus-visible { outline: 3px solid ${FOCUS.onDark}; outline-offset: 3px; }
        .kiosk-lang-half {
          display: flex;
          align-items: center;
          padding: 0 16px;
          border-radius: 999px;
          font-size: 16px;
          font-weight: 600;
          color: rgba(251, 247, 242, 0.62);
          transition: background .15s ease, color .15s ease;
        }
        .kiosk-lang-half.is-on { background: ${COLOR.amber}; color: ${COLOR.umber}; font-weight: 700; }
        @media (max-width: 600px) {
          .kiosk-lang { min-height: ${SIZE.touch - 16}px; }
          .kiosk-lang-half { padding: 0 12px; font-size: 15px; }
        }
      `}</style>
    </>
  );
}
