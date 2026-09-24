/**
 * The script the totem is set in.
 *
 * Two things are called "language" and they are not the same size. The
 * **screen** has copy in two, English and Hindi. The **conversation** can be in
 * any of the languages the brain declares, and there is no picker for it: Tess
 * hears the customer's language and switches both legs herself. In Tamil the
 * voice is Tamil and the screen stays English — there is no Tamil screen.
 */

import { FONT } from './brand';

export type Language = 'en' | 'hi';

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
  /** What the visit is, in three steps, for the welcome tray. */
  steps: readonly [string, string, string];
  /** Above the answers: the voice leads, the chips follow. */
  sayOrTap: string;
  swipeHint: string;
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
  chooseCard: string;
  details: string;
  previousCard: string;
  nextCard: string;
  showCard: string;
  rowFee: string;
  rowWaiver: string;
  rowReward: string;
  rowHero: string;
  detailNeeds: string;
  detailBack: string;
  consentTitle: string;
  consentAgree: string;
  consentHint: string;
  valueHint: string;
  valueMasked: string;
  valueSubmit: string;
  handoffTitle: string;
  restart: string;
}

const EN: Strings = {
  assistant: 'Tess',
  assistantRole: 'AI assistant',
  attractTitle: 'Find the right Vantage card',
  attractBody: 'Four questions, out loud. Tess ranks three cards for you and gives you a code for the desk.',
  steps: ['Answer four quick questions', 'See three cards picked for you', 'Take a code to the desk'],
  sayOrTap: 'Say your answer, or tap one',
  swipeHint: 'Ask Tess about any card, or swipe',
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
  chooseCard: 'Choose',
  details: 'Details',
  previousCard: 'Previous card',
  nextCard: 'Next card',
  showCard: 'Show card',
  rowFee: 'Annual fee',
  rowWaiver: 'Fee waiver',
  rowReward: 'Rewards',
  rowHero: 'Stand-out',
  detailNeeds: 'What it asks for',
  detailBack: 'All three cards',
  consentTitle: 'Before we hand you over',
  consentAgree: 'I agree',
  consentHint: 'Or just say yes.',
  valueHint: 'Say it, or type it and press Enter.',
  valueMasked: 'On screen as',
  valueSubmit: 'Continue',
  handoffTitle: 'Show this at the desk',
  restart: 'Start over',
};

const HI: Strings = {
  assistant: 'टेस',
  assistantRole: 'एआई सहायक',
  attractTitle: 'अपने लिए सही वैंटेज कार्ड चुनिए',
  attractBody: 'चार सवाल, बोलकर। टेस आपके लिए तीन कार्ड चुनेगी और डेस्क के लिए एक कोड देगी।',
  steps: ['चार छोटे सवालों के जवाब दीजिए', 'आपके लिए चुने तीन कार्ड देखिए', 'डेस्क के लिए कोड लीजिए'],
  sayOrTap: 'जवाब बोलिए, या किसी एक पर टैप कीजिए',
  swipeHint: 'किसी भी कार्ड के बारे में टेस से पूछिए, या स्वाइप कीजिए',
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
  chooseCard: 'चुनें',
  details: 'विवरण',
  previousCard: 'पिछला कार्ड',
  nextCard: 'अगला कार्ड',
  showCard: 'कार्ड दिखाएँ',
  rowFee: 'वार्षिक शुल्क',
  rowWaiver: 'शुल्क माफी',
  rowReward: 'रिवॉर्ड',
  rowHero: 'खास बात',
  detailNeeds: 'क्या चाहिए',
  detailBack: 'तीनों कार्ड',
  consentTitle: 'आगे बढ़ने से पहले',
  consentAgree: 'मैं सहमत हूँ',
  consentHint: 'या बस हाँ कहिए।',
  valueHint: 'बोलिए, या टाइप करके एंटर दबाइए।',
  valueMasked: 'स्क्रीन पर',
  valueSubmit: 'आगे बढ़ें',
  handoffTitle: 'डेस्क पर यह दिखाइए',
  restart: 'फिर से शुरू करें',
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
