/**
 * The Petwell Health Hub — the hospital's library of pet-health articles.
 *
 * Written for this demo in the shape a vet chain's resource hub uses: a dated
 * card, an "on this page" contents list, short sections with warning and tip
 * callouts, an FAQ, and a call to book the service the article is about. The
 * text is original and general — it is not veterinary advice.
 *
 * `backend/hub.py` carries the same ids with the facts the assistant may quote,
 * so it can open an article and answer from it. Keep the ids identical.
 */

import puppy from './assets/puppy.webp';
import cat from './assets/cat.webp';
import dental from './assets/dental.webp';
import seniorDog from './assets/senior-dog.webp';
import atHome from './assets/at-home.webp';
import grooming from './assets/grooming.webp';

export type HubTag = 'Dogs' | 'Cats' | 'Seasonal' | 'Prevention';

export interface Section {
  heading: string;
  body?: string[];
  bullets?: string[];
  callout?: { kind: 'warning' | 'tip'; text: string };
  table?: { head: [string, string]; rows: [string, string][] };
}

export interface Article {
  id: string;
  title: string;
  dek: string;
  date: string; // ISO
  readMins: number;
  tags: HubTag[];
  image: string;
  /** The service the article's call to action books. */
  serviceId: string;
  sections: Section[];
  faqs: { q: string; a: string }[];
}

export const ARTICLES: Article[] = [
  {
    id: 'parvovirus',
    title: 'Parvovirus in Puppies: Signs, Treatment and the Vaccine Schedule',
    dek: 'A fast-moving virus that unvaccinated puppies catch from the ground they walk on — and how a few vaccine visits prevent it.',
    date: '2026-10-01',
    readMins: 6,
    tags: ['Dogs', 'Prevention'],
    image: puppy,
    serviceId: 'vaccination',
    sections: [
      {
        heading: 'Overview',
        body: [
          'Canine parvovirus attacks the lining of the gut and the immune system. It spreads through infected stool, and it survives on soil, shoes and floors for months — so a puppy can catch it without ever meeting a sick dog.',
          'Puppies under six months and dogs that have missed their boosters are most at risk.',
        ],
        callout: {
          kind: 'warning',
          text: 'A puppy with parvo can become critically dehydrated within a day or two. Repeated vomiting or bloody diarrhoea is an emergency.',
        },
      },
      {
        heading: 'Signs to watch for',
        bullets: [
          'Repeated vomiting',
          'Watery or bloody, strong-smelling diarrhoea',
          'Sudden tiredness and weakness',
          'Refusing food and water',
          'A tender, bloated belly',
        ],
      },
      {
        heading: 'How it is treated',
        body: [
          'There is no medicine that kills the virus itself. Treatment supports the puppy while its immune system fights back: intravenous fluids, anti-nausea medicine, antibiotics against secondary infection, and careful feeding — usually in an isolation ward.',
        ],
        callout: {
          kind: 'tip',
          text: 'Keep a recovering dog away from other dogs, and clean with a diluted bleach solution — most household cleaners do not kill parvo.',
        },
      },
      {
        heading: 'The vaccine schedule',
        table: {
          head: ['Age', 'What to book'],
          rows: [
            ['6–8 weeks', 'First core vaccine (covers parvovirus)'],
            ['10–12 weeks', 'Second dose'],
            ['14–16 weeks', 'Third dose'],
            ['Every year', 'Booster to keep protection up'],
          ],
        },
      },
    ],
    faqs: [
      {
        q: 'Can a vaccinated dog still get parvo?',
        a: 'Rarely. Protection is strongest when the puppy series is complete and yearly boosters are on time.',
      },
      {
        q: 'Can my puppy go out before the last dose?',
        a: 'Carry them rather than letting them walk on public ground, and avoid dogs of unknown vaccine status until a week after the final dose.',
      },
    ],
  },
  {
    id: 'diwali-safety',
    title: 'Diwali with Pets: Firecrackers, Sweets and Smoke',
    dek: 'Five simple steps that keep dogs and cats calm and safe through the festival week.',
    date: '2026-10-04',
    readMins: 4,
    tags: ['Seasonal', 'Dogs', 'Cats'],
    image: atHome,
    serviceId: 'general-consult',
    sections: [
      {
        heading: 'Overview',
        body: [
          'A pet hears fireworks several times louder than we do. Fear can make even a calm dog bolt through an open door, and festive sweets and decorations bring their own risks.',
        ],
      },
      {
        heading: 'A calm room',
        bullets: [
          'Set up an inner room with their bed, water and a worn T-shirt of yours',
          'Close curtains and play steady background sound',
          'Walk dogs early in the evening, before the noise starts — on a lead',
          'Make sure the collar tag and microchip details are up to date',
        ],
        callout: {
          kind: 'tip',
          text: 'If your pet panicked last year, book a consult a week ahead — your vet can suggest calming options that are safe for them.',
        },
      },
      {
        heading: 'Sweets and decorations',
        bullets: [
          'Chocolate, raisins, xylitol-sweetened mithai and ghee-rich sweets are all risky',
          'Keep diyas and candles out of reach of tails and paws',
          'Tinsel, ribbon and rangoli colours can block or irritate the gut',
        ],
        callout: {
          kind: 'warning',
          text: 'Vomiting, a racing heart or tremors after eating sweets needs a vet the same night.',
        },
      },
    ],
    faqs: [
      {
        q: 'Should I give my dog a sedative for fireworks?',
        a: 'Only one your vet has prescribed for that pet. Human medicines can be dangerous for animals.',
      },
    ],
  },
  {
    id: 'cat-urinary',
    title: 'Why Is My Cat Straining to Pee?',
    dek: 'Straining in the litter box can be cystitis, crystals — or, in male cats, a blockage that cannot wait.',
    date: '2026-09-27',
    readMins: 5,
    tags: ['Cats'],
    image: cat,
    serviceId: 'general-consult',
    sections: [
      {
        heading: 'Overview',
        body: [
          'Urinary problems in cats are common and often linked to stress, low water intake and diet. Most cases settle with treatment, but a blocked urethra is an emergency.',
        ],
        callout: {
          kind: 'warning',
          text: 'A male cat who strains and produces little or no urine needs a vet within hours, day or night.',
        },
      },
      {
        heading: 'Signs',
        bullets: [
          'Many trips to the litter box with little result',
          'Crying while passing urine',
          'Blood in the urine',
          'Peeing outside the box',
          'Licking the genital area',
        ],
      },
      {
        heading: 'At home',
        bullets: [
          'More water: wet food, a fountain, bowls in several rooms',
          'One litter box per cat, plus one, kept clean',
          'A calm routine — changes at home can trigger flare-ups',
        ],
      },
    ],
    faqs: [
      {
        q: 'What will the vet check?',
        a: 'Usually a urine test, and sometimes an X-ray or ultrasound to look for crystals or stones.',
      },
    ],
  },
  {
    id: 'dental-care',
    title: 'Dental Disease in Dogs and Cats — and Why Cleaning Is Done Under Anaesthesia',
    dek: 'Bad breath is often the first sign of gum disease. Here is what a proper dental clean involves.',
    date: '2026-09-20',
    readMins: 5,
    tags: ['Dogs', 'Cats', 'Prevention'],
    image: dental,
    serviceId: 'dental',
    sections: [
      {
        heading: 'Overview',
        body: [
          'Most dogs and cats show some gum disease by middle age. Plaque hardens into tartar, gums pull back, and infection can reach the roots of the teeth.',
        ],
      },
      {
        heading: 'Signs',
        bullets: ['Bad breath', 'Red or bleeding gums', 'Chewing on one side', 'Dropping food', 'Pawing at the mouth'],
      },
      {
        heading: 'Why anaesthesia',
        body: [
          'Most disease hides below the gum line. A safe, monitored anaesthetic lets the vet scale under the gums, X-ray the roots and treat painful teeth properly — something an awake pet will not allow.',
        ],
        callout: {
          kind: 'tip',
          text: 'A pre-anaesthetic blood test is usually done first, especially for older pets.',
        },
      },
    ],
    faqs: [
      {
        q: 'How often should I brush?',
        a: 'Daily is ideal, with a pet toothpaste — human toothpaste is not safe for pets to swallow.',
      },
    ],
  },
  {
    id: 'ticks-fleas',
    title: 'Ticks and Fleas After the Monsoon: A Prevention Plan',
    dek: 'Humid months bring a tick season that can carry blood parasites. A simple routine keeps it under control.',
    date: '2026-09-12',
    readMins: 4,
    tags: ['Dogs', 'Seasonal', 'Prevention'],
    image: grooming,
    serviceId: 'skin',
    sections: [
      {
        heading: 'Overview',
        body: [
          'Ticks do more than itch — some carry infections that lower the platelet count and cause fever and weakness. Fleas cause allergies and can pass on tapeworm.',
        ],
      },
      {
        heading: 'A monthly routine',
        bullets: [
          'A vet-recommended spot-on, tablet or collar — on schedule, all year',
          'Check ears, between toes and under the collar after walks',
          'Wash bedding weekly in hot water',
          'Treat every pet in the house at the same time',
        ],
        callout: {
          kind: 'warning',
          text: 'Fever, pale gums or unusual bruising after a tick bite needs a blood test.',
        },
      },
    ],
    faqs: [
      {
        q: 'How do I remove a tick?',
        a: 'Grip it close to the skin with fine tweezers or a tick hook and pull steadily. Do not crush it or apply oil.',
      },
    ],
  },
  {
    id: 'senior-checks',
    title: 'Senior Pet Health Checks: What to Test After Seven',
    dek: 'Older pets hide illness well. A yearly senior check finds kidney, thyroid and joint problems early.',
    date: '2026-09-05',
    readMins: 5,
    tags: ['Dogs', 'Cats', 'Prevention'],
    image: seniorDog,
    serviceId: 'diagnostics',
    sections: [
      {
        heading: 'Overview',
        body: [
          'From about seven years (earlier for giant breeds), pets age faster than we notice. Early changes in blood and urine often appear months before any outward sign.',
        ],
      },
      {
        heading: 'What a senior check covers',
        table: {
          head: ['Test', 'What it looks for'],
          rows: [
            ['Blood count and chemistry', 'Anaemia, kidney and liver changes'],
            ['Urine test', 'Early kidney disease, diabetes, infection'],
            ['Thyroid level', 'Over-active thyroid in cats, under-active in dogs'],
            ['Blood pressure', 'Hypertension, common with kidney disease'],
            ['Joint exam', 'Arthritis and muscle loss'],
          ],
        },
        callout: { kind: 'tip', text: 'Bring a list of any changes in thirst, appetite, weight or sleep — small details help.' },
      },
    ],
    faqs: [
      {
        q: 'How often should a senior pet be checked?',
        a: 'Once a year at least, and every six months for pets with an ongoing condition.',
      },
    ],
  },
];

export const getArticle = (id: string | null | undefined) => ARTICLES.find((a) => a.id === id);
