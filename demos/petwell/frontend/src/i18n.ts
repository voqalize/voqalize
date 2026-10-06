/**
 * The website's two languages — English and Hindi.
 *
 * Nobody picks a language: Tushar hears which one the visitor speaks, switches
 * to it, and the page follows him into Hindi; in any other language it stays English (the brain's `language_changed` says which
 * with `screen_language`). Branch names and addresses stay as written, and the
 * Health Hub articles are in English in both.
 */

import type { Service } from './catalog';

export type Lang = 'en' | 'hi';

/** Each language Tushar speaks, in its own script — for the header's badge. */
export const NATIVE_NAME: Record<string, string> = {
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
};

export const FONT: Record<Lang, string> = {
  en: '"Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  hi: '"Noto Sans Devanagari", "Inter", ui-sans-serif, system-ui, sans-serif',
};

const EN = {
  // chrome
  ticker: 'Petwell Kolkata — opening soon! · Now open 24x7 for emergencies · 15 branches across 9 cities',
  navHome: 'Home',
  navServices: 'Treatments & Services',
  navLocations: 'Locations',
  navHub: 'Health Hub',
  navAtHome: 'Petwell@Home',
  emergency: '24x7 Emergency',
  book: 'Book an Appointment',
  talk: 'Talk to Tushar',
  hospitals: 'Veterinary Hospitals',
  // home
  heroKicker: 'Primary care · Specialty care · 24x7 emergency',
  heroTitle: 'Expert vets, modern hospitals — and care that never closes',
  heroLead:
    'From vaccinations to advanced surgery, Petwell looks after dogs, cats and exotic pets in 15 hospitals across India.',
  heroVoice: 'Prefer to talk? Tap the mic and just speak — Tushar switches to your language by himself.',
  speaking: 'Speaking',
  statVets: 'Qualified vets',
  statBranches: 'Branches',
  statCities: 'Cities',
  statOpen: 'Emergency care',
  careTitle: 'Care for every stage of life',
  primary: 'Primary care',
  specialty: 'Specialty care',
  viewAll: 'View all',
  nearTitle: 'Find a Petwell near you',
  nearLead: '15 branches across 9 cities. Pick a city to see its branches.',
  homeTitle: 'Petwell@Home — the vet comes to you',
  homeLead:
    'No car rides, no waiting rooms. Vaccinations, minor illness and injury consults, blood sample collection and physiotherapy — at your doorstep.',
  homeBook: 'Book a home visit',
  whyTitle: 'Why pet owners choose us',
  quote:
    '“When Bruno got sick at midnight, the team at Petwell had him on a drip within the hour. They explained every step, and called us every morning until he was home.”',
  quoteBy: 'Meera, with Bruno (4)',
  hubTitle: 'From the Health Hub',
  hubLead: 'Practical, vet-written guides for pet owners.',
  readMore: 'Read article',
  // pages
  servicesTitle: 'Veterinary treatments & services',
  servicesLead: 'Everyday care and specialist treatment, under one roof.',
  locationsTitle: 'Locations across the country',
  allCities: 'All cities',
  emergencyBranch: '24x7 Emergency',
  openingSoon: 'Opening soon',
  bookHere: 'Book here',
  hubPageTitle: 'Petwell Health Hub',
  hubPageLead: 'Expert pet-health information, treatment options and answers to common questions — all in one place.',
  all: 'All',
  minRead: 'min read',
  onThisPage: 'On this page',
  faqs: 'FAQs',
  bookThis: 'Book',
  backToHub: 'Health Hub',
  notAdvice: 'General information, not a diagnosis. Your vet will examine your pet.',
  atHomeTitle: 'Veterinary home visits',
  atHomeLead:
    'Tired of stressful vet trips and anxious pets? We bring expert veterinary care to your doorstep — in the place your pet loves most.',
  stressFree: 'Stress-free',
  stressFreeText: 'No cars, no waiting rooms, no fear.',
  convenient: 'Convenient',
  convenientText: 'Skip the commute and save time.',
  personal: 'Personal',
  personalText: 'One-on-one care at home.',
  trusted: 'Trusted',
  trustedText: 'The same Petwell vets and standards.',
  footerAbout: 'A Voqalize demo · Petwell is a fictional hospital chain.',
  photos: 'Photos: Unsplash',
  // booking
  bookingTitle: 'Book an Appointment',
  stepVisit: 'Visit',
  stepLocation: 'Location',
  stepReason: 'Reason',
  stepTime: 'Time',
  stepDetails: 'Details',
  stepReview: 'Review',
  back: 'Back',
  clinicVisit: 'Clinic Visit',
  clinicVisitSub: 'Everyday and specialty care at a Petwell hospital near you',
  homeVisit: 'Petwell@Home',
  homeVisitSub: 'Vaccinations, minor illness, blood samples and physio — at your door',
  chooseCity: 'Choose your city',
  whereVet: 'Where should our vet come?',
  branchesIn: 'Branches in',
  nearestIn: 'Nearest branch in',
  soonNote: 'is opening soon. Please choose another city for now.',
  whatFor: "What's the visit for?",
  everyday: 'Everyday care',
  specialtyCare: 'Specialty care',
  atHomeGroup: 'At home',
  pickTime: 'Pick a day and time',
  today: 'Today',
  fullyBooked: 'Fully booked on this day — please pick another.',
  yourDetails: 'Your details',
  name: 'Your Name',
  petName: "Your Pet's Name",
  petType: 'Pet type',
  phone: 'Phone Number',
  email: 'Email ID (optional)',
  address: 'Home address / locality',
  message: 'Message',
  continue: 'Continue',
  checkSend: 'Check and send',
  send: 'Send Request',
  willCall: 'The branch will call you to confirm your appointment.',
  sent: 'Request sent',
  refIs: 'Your reference is',
  callShortly: 'The branch will call you shortly to confirm.',
  another: 'Book another appointment',
  serviceType: 'Service type',
  branch: 'Branch',
  reason: 'Reason',
  when: 'When',
  pet: 'Pet',
  owner: 'Owner',
  sosTitle: 'Emergency? Come in now.',
  sosLead: 'Our emergency hospitals are open 24x7. Call ahead so the team is ready.',
  sosBranches: '24x7 emergency branches in',
  pets: { dog: 'Dog', cat: 'Cat', bird: 'Bird', rabbit: 'Rabbit', other: 'Other' } as Record<string, string>,
  // desk
  deskRole: 'AI front desk',
  deskHint: 'Tap the mic to talk to Tushar',
  deskState: { idle: 'Here to help', listening: 'Listening', thinking: 'Checking', speaking: 'Speaking' } as Record<
    string,
    string
  >,
  deskOffline: 'Offline',
  speaks: 'Speaks English, हिन्दी, বাংলা, मराठी, தமிழ், తెలుగు and more',
};

export type Strings = typeof EN;

const HI: Strings = {
  ticker: 'पेटवेल कोलकाता — जल्द आ रहा है! · इमरजेंसी के लिए अब 24x7 खुला · 9 शहरों में 15 ब्रांच',
  navHome: 'होम',
  navServices: 'इलाज और सेवाएँ',
  navLocations: 'लोकेशन',
  navHub: 'हेल्थ हब',
  navAtHome: 'पेटवेल@होम',
  emergency: '24x7 इमरजेंसी',
  book: 'अपॉइंटमेंट बुक करें',
  talk: 'तुषार से बात करें',
  hospitals: 'वेटरनरी हॉस्पिटल्स',
  heroKicker: 'प्राइमरी केयर · स्पेशलिटी केयर · 24x7 इमरजेंसी',
  heroTitle: 'अनुभवी डॉक्टर, आधुनिक हॉस्पिटल — और देखभाल जो कभी बंद नहीं होती',
  heroLead:
    'टीकाकरण से लेकर एडवांस सर्जरी तक, पेटवेल पूरे भारत में 15 हॉस्पिटलों में कुत्तों, बिल्लियों और एक्ज़ॉटिक पेट्स की देखभाल करता है।',
  heroVoice: 'बोलकर बुक करना है? माइक दबाइए और बोलिए — तुषार अपने आप आपकी भाषा में बात करेंगे।',
  speaking: 'भाषा',
  statVets: 'योग्य डॉक्टर',
  statBranches: 'ब्रांच',
  statCities: 'शहर',
  statOpen: 'इमरजेंसी केयर',
  careTitle: 'ज़िंदगी के हर पड़ाव की देखभाल',
  primary: 'प्राइमरी केयर',
  specialty: 'स्पेशलिटी केयर',
  viewAll: 'सभी देखें',
  nearTitle: 'अपने पास पेटवेल खोजें',
  nearLead: '9 शहरों में 15 ब्रांच। ब्रांच देखने के लिए शहर चुनें।',
  homeTitle: 'पेटवेल@होम — डॉक्टर आपके घर',
  homeLead:
    'न गाड़ी का सफ़र, न वेटिंग रूम। टीकाकरण, छोटी बीमारी या चोट की जाँच, ब्लड सैंपल और फ़िज़ियोथेरेपी — आपके दरवाज़े पर।',
  homeBook: 'होम विज़िट बुक करें',
  whyTitle: 'पेट पैरेंट्स हमें क्यों चुनते हैं',
  quote:
    '“आधी रात को जब ब्रूनो बीमार हुआ, पेटवेल की टीम ने एक घंटे में उसे ड्रिप पर लगा दिया। हर कदम समझाया, और जब तक वह घर नहीं आया, हर सुबह फ़ोन किया।”',
  quoteBy: 'मीरा, ब्रूनो (4) के साथ',
  hubTitle: 'हेल्थ हब से',
  hubLead: 'पेट पैरेंट्स के लिए डॉक्टरों की लिखी काम की गाइड।',
  readMore: 'लेख पढ़ें',
  servicesTitle: 'वेटरनरी इलाज और सेवाएँ',
  servicesLead: 'रोज़मर्रा की देखभाल और स्पेशलिस्ट इलाज, एक ही छत के नीचे।',
  locationsTitle: 'देश भर में हमारी लोकेशन',
  allCities: 'सभी शहर',
  emergencyBranch: '24x7 इमरजेंसी',
  openingSoon: 'जल्द आ रहा है',
  bookHere: 'यहाँ बुक करें',
  hubPageTitle: 'पेटवेल हेल्थ हब',
  hubPageLead: 'पेट हेल्थ की जानकारी, इलाज के विकल्प और आम सवालों के जवाब — एक ही जगह। (लेख अंग्रेज़ी में हैं)',
  all: 'सभी',
  minRead: 'मिनट',
  onThisPage: 'इस पेज पर',
  faqs: 'अक्सर पूछे जाने वाले सवाल',
  bookThis: 'बुक करें',
  backToHub: 'हेल्थ हब',
  notAdvice: 'यह सामान्य जानकारी है, निदान नहीं। डॉक्टर आपके पेट की जाँच करेंगे।',
  atHomeTitle: 'घर पर वेटरनरी विज़िट',
  atHomeLead:
    'डॉक्टर के पास ले जाने की परेशानी और घबराए हुए पेट? हम अनुभवी डॉक्टर को आपके घर लाते हैं — उस जगह जहाँ आपका पेट सबसे सहज है।',
  stressFree: 'बिना तनाव',
  stressFreeText: 'न गाड़ी, न वेटिंग रूम, न डर।',
  convenient: 'आसान',
  convenientText: 'आने-जाने का समय बचाइए।',
  personal: 'व्यक्तिगत',
  personalText: 'घर पर पूरा ध्यान।',
  trusted: 'भरोसेमंद',
  trustedText: 'वही पेटवेल डॉक्टर और वही स्टैंडर्ड।',
  footerAbout: 'एक Voqalize डेमो · पेटवेल एक काल्पनिक हॉस्पिटल चेन है।',
  photos: 'फ़ोटो: Unsplash',
  bookingTitle: 'अपॉइंटमेंट बुक करें',
  stepVisit: 'विज़िट',
  stepLocation: 'लोकेशन',
  stepReason: 'वजह',
  stepTime: 'समय',
  stepDetails: 'जानकारी',
  stepReview: 'रिव्यू',
  back: 'पीछे',
  clinicVisit: 'क्लिनिक विज़िट',
  clinicVisitSub: 'आपके पास के पेटवेल हॉस्पिटल में रोज़मर्रा और स्पेशलिटी केयर',
  homeVisit: 'पेटवेल@होम',
  homeVisitSub: 'टीकाकरण, छोटी बीमारी, ब्लड सैंपल और फ़िज़ियो — आपके घर पर',
  chooseCity: 'अपना शहर चुनें',
  whereVet: 'डॉक्टर कहाँ आएँ?',
  branchesIn: 'ब्रांच —',
  nearestIn: 'नज़दीकी ब्रांच —',
  soonNote: 'जल्द खुल रहा है। अभी के लिए कोई दूसरा शहर चुनें।',
  whatFor: 'विज़िट किस लिए है?',
  everyday: 'रोज़मर्रा की देखभाल',
  specialtyCare: 'स्पेशलिटी केयर',
  atHomeGroup: 'घर पर',
  pickTime: 'दिन और समय चुनें',
  today: 'आज',
  fullyBooked: 'इस दिन सब बुक है — कोई और दिन चुनें।',
  yourDetails: 'आपकी जानकारी',
  name: 'आपका नाम',
  petName: 'पेट का नाम',
  petType: 'पेट',
  phone: 'फ़ोन नंबर',
  email: 'ईमेल (वैकल्पिक)',
  address: 'घर का पता / इलाका',
  message: 'संदेश',
  continue: 'आगे बढ़ें',
  checkSend: 'जाँचें और भेजें',
  send: 'रिक्वेस्ट भेजें',
  willCall: 'ब्रांच आपको अपॉइंटमेंट कन्फ़र्म करने के लिए कॉल करेगी।',
  sent: 'रिक्वेस्ट भेज दी गई',
  refIs: 'आपका रेफ़रेंस नंबर है',
  callShortly: 'ब्रांच जल्द ही कन्फ़र्म करने के लिए कॉल करेगी।',
  another: 'एक और अपॉइंटमेंट बुक करें',
  serviceType: 'सेवा',
  branch: 'ब्रांच',
  reason: 'वजह',
  when: 'कब',
  pet: 'पेट',
  owner: 'नाम',
  sosTitle: 'इमरजेंसी? अभी आइए।',
  sosLead: 'हमारे इमरजेंसी हॉस्पिटल 24x7 खुले हैं। पहले फ़ोन कर दें ताकि टीम तैयार रहे।',
  sosBranches: '24x7 इमरजेंसी ब्रांच —',
  pets: { dog: 'कुत्ता', cat: 'बिल्ली', bird: 'पक्षी', rabbit: 'खरगोश', other: 'अन्य' },
  deskRole: 'AI फ़्रंट डेस्क',
  deskHint: 'तुषार से बात करने के लिए माइक दबाइए',
  deskState: { idle: 'मदद के लिए हाज़िर', listening: 'सुन रहे हैं', thinking: 'देख रहे हैं', speaking: 'बोल रहे हैं' },
  deskOffline: 'ऑफ़लाइन',
  speaks: 'English, हिन्दी, বাংলা, मराठी, தமிழ், తెలుగు और कई भाषाएँ बोलते हैं',
};

export function strings(lang: Lang): Strings {
  return lang === 'hi' ? HI : EN;
}

const CITY_HI: Record<string, string> = {
  Goa: 'गोवा',
  Gurugram: 'गुरुग्राम',
  Hyderabad: 'हैदराबाद',
  Jaipur: 'जयपुर',
  Kolkata: 'कोलकाता',
  Lucknow: 'लखनऊ',
  Mumbai: 'मुंबई',
  'New Delhi': 'नई दिल्ली',
  Noida: 'नोएडा',
};

export const cityName = (city: string, lang: Lang) => (lang === 'hi' ? CITY_HI[city] ?? city : city);

const SERVICE_HI: Record<string, [string, string]> = {
  'general-consult': ['जनरल कंसल्टेशन', 'जाँच और कोई भी हेल्थ चिंता'],
  vaccination: ['टीकाकरण', 'पपी, किटन और बूस्टर टीके'],
  grooming: ['ग्रूमिंग', 'नहलाना, ट्रिम, नाखून और कोट केयर'],
  dental: ['दाँतों की देखभाल', 'सफ़ाई, स्केलिंग, दाँत निकालना'],
  skin: ['स्किन और एलर्जी', 'खुजली, रैश, टिक और पिस्सू'],
  diagnostics: ['जाँच (एक्स-रे, अल्ट्रासाउंड, लैब)', 'इमेजिंग और लैब टेस्ट'],
  cardiology: ['कार्डियोलॉजी', 'दिल और साँस'],
  orthopaedics: ['ऑर्थोपेडिक्स', 'हड्डी, जोड़ और फ़्रैक्चर'],
  oncology: ['कैंसर केयर', 'गाँठ, ट्यूमर, कीमोथेरेपी'],
  neurology: ['न्यूरोलॉजी', 'दिमाग़, रीढ़ और नसें'],
  'eye-care': ['आँखों की देखभाल', 'आँखों की समस्याएँ'],
  'exotic-pets': ['एक्ज़ॉटिक पेट्स', 'पक्षी, खरगोश, रेप्टाइल'],
  physiotherapy: ['फ़िज़ियोथेरेपी और रिहैब', 'रिकवरी और चलना-फिरना'],
  'home-vaccination': ['घर पर टीकाकरण', 'गाड़ी के सफ़र के बिना टीके'],
  'home-consult': ['छोटी बीमारी या चोट की जाँच', 'डॉक्टर आपके दरवाज़े पर'],
  'home-blood-sample': ['ब्लड सैंपल कलेक्शन', 'घर से लैब टेस्ट'],
  'home-physio': ['घर पर फ़िज़ियोथेरेपी', 'जानी-पहचानी जगह पर रिहैब'],
};

export function serviceName(s: Service, lang: Lang): string {
  return lang === 'hi' ? SERVICE_HI[s.id]?.[0] ?? s.name : s.name;
}

export function serviceBlurb(s: Service, lang: Lang): string {
  return lang === 'hi' ? SERVICE_HI[s.id]?.[1] ?? s.blurb : s.blurb;
}

export function groupName(g: Service['group'], lang: Lang): string {
  const t = strings(lang);
  return g === 'Everyday care' ? t.everyday : g === 'Specialty care' ? t.specialtyCare : t.atHomeGroup;
}

/** Dates in the page's language. */
export function locale(lang: Lang): string {
  return lang === 'hi' ? 'hi-IN' : 'en-IN';
}
