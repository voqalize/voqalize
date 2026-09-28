/**
 * Every fixed string on the totem, in English.
 *
 * The screen is English whatever language Tanvi is speaking. She follows the
 * customer into Hindi, Tamil or any language the brain declares, and only her
 * voice and her ears move: the form stays as the bank wrote it. The variable
 * strings — the question, the reasons, the card copy, the consent bullets —
 * arrive from the brain, which writes them in Python and never lets a model
 * author one.
 */

interface Copy {
  assistant: string;
  assistantRole: string;
  attractTitle: string;
  attractBody: string;
  /** What the visit is, as steps, for the welcome tray. */
  steps: readonly [string, string, string];
  /** Above the answers: the hand leads, and Tanvi is there to be asked. */
  tapOrAsk: string;
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

export const COPY: Copy = {
  assistant: 'Tanvi',
  assistantRole: 'AI assistant',
  attractTitle: 'Find the right Vantage card',
  attractBody: 'Tap your answers on the screen. Ask Tanvi anything along the way.',
  steps: ['Tap through a few quick questions', 'See the cards picked for you', 'Take a code to the desk'],
  tapOrAsk: 'Tap your answer, or ask Tanvi anything',
  swipeHint: 'Ask Tanvi about any card, or swipe',
  confirmPrompt: 'Is this right?',
  confirmYes: 'Yes, that’s right',
  confirmHint: 'Not quite? Type it again.',
  eligibilityTitle: 'Where you stand',
  eligibilityNext: 'Show me the cards',
  lineLabel: 'Indicative limit',
  bankerConfirms: 'A banker will confirm this at the desk.',
  shortlistTitle: 'Cards for you',
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
  detailBack: 'All the cards',
  consentTitle: 'Before we hand you over',
  consentAgree: 'I agree',
  consentHint: 'Read it through, then tap I agree.',
  valueHint: 'Type it in and press Continue. For your privacy, please don’t say it out loud.',
  valueMasked: 'On screen as',
  valueSubmit: 'Continue',
  handoffTitle: 'Show this at the desk',
  restart: 'Start over',
};

/**
 * What the eligibility chip calls each band.
 *
 * `band` arrives as a wire token (`wide`, `standard`, `secured`) and a wire token
 * is not a label. A band this build does not know is printed as it came rather
 * than dropped: an unexplained word on screen beats a missing verdict, and the
 * reasons beside it carry the meaning either way.
 */
const BAND_LABEL: Record<string, string> = {
  wide: 'Our full range',
  standard: 'Our standard range',
  secured: 'Secured card',
};

export function bandLabel(band: string): string {
  return BAND_LABEL[band] ?? band;
}

/**
 * What the ledger calls each field. A field this build does not know is printed
 * from its wire name, readably.
 */
const FIELD_LABEL: Record<string, string> = {
  employment: 'Employment',
  income_band: 'Monthly income',
  existing_cards: 'Cards you hold',
  spend_category: 'Where you spend most',
  mobile: 'Mobile',
  pan: 'PAN',
};

export function fieldLabel(field: string): string {
  const known = FIELD_LABEL[field];
  if (known) return known;
  const words = field.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}
