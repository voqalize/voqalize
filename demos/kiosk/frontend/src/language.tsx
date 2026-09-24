/**
 * The script the totem is set in, and the picker that chooses the conversation's
 * language.
 *
 * Two things are called "language" here and they are not the same size. The
 * **screen** has copy in two, English and Hindi. The **conversation** can be in
 * any of the languages the brain declares. Picking Tamil puts Tess in Tamil and
 * leaves the screen in English — there is no Tamil screen, only a Tamil voice.
 *
 * The picker never moves a leg itself. It tells the brain which language was
 * picked, and the brain moves both legs in one `session.configure(...)`: a page
 * that set one leg would be the half-applied-pair bug, which is silent — the
 * words stay right and only the speaker is wrong.
 */

import type { LanguagePicked } from './actions.gen';
import { COLOR, FOCUS, FONT, SIZE } from './brand';

export type Language = 'en' | 'hi';

/**
 * Every language the conversation can be in. Read off the generated contract,
 * never written down: the brain's `LanguageName` is the one list, and a language
 * added there is a compile error here until it has a label below.
 */
export type LanguageName = LanguagePicked['language'];

/**
 * Each language named in its own script, which is how a customer finds theirs —
 * and the English name beside it, for the one standing next to them. A
 * `Record` over the union, so a missing or stray row does not compile.
 */
const NATIVE: Record<LanguageName, string> = {
  English: 'English',
  Hindi: 'हिन्दी',
  Bengali: 'বাংলা',
  Gujarati: 'ગુજરાતી',
  Kannada: 'ಕನ್ನಡ',
  Malayalam: 'മലയാളം',
  Marathi: 'मराठी',
  Punjabi: 'ਪੰਜਾਬੀ',
  Tamil: 'தமிழ்',
  Telugu: 'తెలుగు',
  Assamese: 'অসমীয়া',
  Bodo: 'बड़ो',
  Dogri: 'डोगरी',
  Kashmiri: 'کٲشُر',
  Konkani: 'कोंकणी',
  Maithili: 'मैथिली',
  Manipuri: 'মৈতৈলোন্',
  Nepali: 'नेपाली',
  Odia: 'ଓଡ଼ିଆ',
  Sanskrit: 'संस्कृतम्',
  Santali: 'ᱥᱟᱱᱛᱟᱲᱤ',
  Sindhi: 'سنڌي',
  Urdu: 'اردو',
};

/** The picker's options, in the brain's own order. */
const LANGUAGES = Object.keys(NATIVE) as LanguageName[];

/** A language written in its own script. */
export function nativeName(name: LanguageName): string {
  return NATIVE[name];
}

/** The screen copy a conversation language gets. Only Hindi has its own. */
export function screenLanguageFor(name: LanguageName): Language {
  return name === 'Hindi' ? 'hi' : 'en';
}

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
  /** The picker's accessible name — it moves Tess's voice, not just the screen. */
  languagePicker: string;
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
  languagePicker: 'Language Tess speaks',
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
  languagePicker: 'टेस किस भाषा में बात करे',
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
 * The language picker in the header — a native `<select>`, on purpose. It is
 * the one control on the totem with twenty-three options, and the platform's own
 * picker is what a phone, a touchscreen, a keyboard and a screen reader already
 * know how to drive. A custom list would have to earn every one of those back.
 *
 * It follows Tess as well as leading her: when she switches because she heard
 * the customer speak Tamil, `value` moves to Tamil and the picker shows it. Picking
 * English is the way back from a switch the customer did not want — the model
 * decided it from what it heard, and a hearing can be wrong.
 */
export function LanguageSelect({
  value,
  screen,
  onChange,
}: {
  /** The language the conversation is in. */
  value: LanguageName;
  /** The screen's copy, for the picker's own label. */
  screen: Language;
  onChange: (language: LanguageName) => void;
}) {
  return (
    <>
      <select
        className="kiosk-lang"
        value={value}
        aria-label={strings(screen).languagePicker}
        onChange={(event) => onChange(event.target.value as LanguageName)}
      >
        {LANGUAGES.map((name) => (
          <option key={name} value={name}>
            {name === 'English' ? 'English' : `${NATIVE[name]} · ${name}`}
          </option>
        ))}
      </select>
      <style>{`
        .kiosk-lang {
          appearance: none;
          min-height: 44px;
          max-width: 150px;
          padding: 0 36px 0 16px;
          border-radius: ${SIZE.pill}px;
          border: 1px solid ${COLOR.rule};
          /* The chevron, drawn inline: one image, no icon font to load. */
          background: ${COLOR.surface}
            url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' fill='none' stroke='%230F3B2E' stroke-width='2'/%3E%3C/svg%3E")
            no-repeat right 14px center;
          color: ${COLOR.brand};
          font: inherit;
          font-size: 15px;
          font-weight: 600;
          text-overflow: ellipsis;
          cursor: pointer;
        }
        .kiosk-lang:hover { border-color: ${COLOR.brand}; }
        .kiosk-lang:focus-visible { outline: 3px solid ${FOCUS.ring}; outline-offset: 2px; }
        .kiosk-lang option { background: ${COLOR.surface}; color: ${COLOR.ink}; }
      `}</style>
    </>
  );
}
