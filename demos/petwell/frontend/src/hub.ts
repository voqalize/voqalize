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
import dogMouth from './assets/dog-mouth.webp';
import chewToy from './assets/chew-toy.webp';
import catYawn from './assets/cat-yawn.webp';
import dogYawn from './assets/dog-yawn.webp';
import rabbit from './assets/rabbit.webp';

export type HubTag = 'Dogs' | 'Cats' | 'Dental' | 'Seasonal' | 'Prevention';

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
    tags: ['Dental', 'Dogs', 'Cats', 'Prevention'],
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
    id: 'periodontal-disease',
    title: 'Periodontal Disease in Dogs and Cats: The Four Stages and What Each Needs',
    dek: 'Gum disease is the most common illness vets see in adult pets — and it is silent until it hurts. Here is how it progresses.',
    date: '2026-09-30',
    readMins: 6,
    tags: ['Dental', 'Dogs', 'Cats'],
    image: dogMouth,
    serviceId: 'dental',
    sections: [
      {
        heading: 'Overview',
        body: [
          'Periodontal disease starts as plaque — a film of bacteria on the teeth. Within days it hardens into tartar, which irritates the gums. Left alone, the infection works down along the root, loosening the tooth from the jaw.',
          'Small breeds, flat-faced dogs and cats are most prone, but almost every pet over three years old has some degree of it.',
        ],
        callout: {
          kind: 'warning',
          text: 'Pets rarely stop eating because of dental pain. Bad breath and chewing on one side are often the only clues.',
        },
      },
      {
        heading: 'The four stages',
        table: {
          head: ['Stage', 'What the vet sees'],
          rows: [
            ['1 — Gingivitis', 'Red gum line, no bone loss. Fully reversible with a clean'],
            ['2 — Early', 'Up to a quarter of the root support lost'],
            ['3 — Moderate', 'A quarter to half of the support lost; pockets around roots'],
            ['4 — Advanced', 'More than half lost; loose teeth, pus, often extraction'],
          ],
        },
      },
      {
        heading: 'Why it matters beyond the mouth',
        body: [
          'Bacteria from infected gums enter the bloodstream every time the pet chews. Advanced dental disease is linked with strain on the heart, kidneys and liver, and with jaw fractures in small dogs whose bone has thinned.',
        ],
      },
      {
        heading: 'Treatment',
        bullets: [
          'A full clean under anaesthesia, scaling above and below the gum line',
          'Dental X-rays to see the roots and bone that cannot be seen from outside',
          'Extraction of teeth that cannot be saved',
          'A home-care plan afterwards — brushing, dental chews or diets',
        ],
        callout: { kind: 'tip', text: 'Stage 1 and 2 are where treatment is quickest and cheapest. A yearly dental check catches them.' },
      },
    ],
    faqs: [
      {
        q: 'Can periodontal disease be reversed?',
        a: 'Gingivitis (stage 1) can. Once bone is lost it cannot grow back, but treatment stops it getting worse.',
      },
      {
        q: 'How often does my pet need a professional clean?',
        a: 'Most need one every one to two years; small breeds and cats with a history of gum disease often need it yearly.',
      },
    ],
  },
  {
    id: 'brushing-teeth',
    title: "How to Brush Your Pet's Teeth at Home: A Step-by-Step Guide",
    dek: 'Two minutes a day does more for your pet’s teeth than anything else. Here is how to build the habit without a fight.',
    date: '2026-09-24',
    readMins: 5,
    tags: ['Dental', 'Dogs', 'Cats', 'Prevention'],
    image: chewToy,
    serviceId: 'dental',
    sections: [
      {
        heading: 'Overview',
        body: [
          'Plaque turns to tartar in about 48 hours, so brushing every day — or at least every other day — keeps it from setting. Most pets accept brushing if it is introduced slowly and paired with something they enjoy.',
        ],
      },
      {
        heading: 'What you need',
        bullets: [
          'A pet toothpaste — flavoured, safe to swallow',
          'A soft pet toothbrush or a finger brush',
          'A few small treats and a calm moment of the day',
        ],
        callout: {
          kind: 'warning',
          text: 'Never use human toothpaste. Fluoride and xylitol in it are harmful to pets when swallowed.',
        },
      },
      {
        heading: 'Step by step, over two weeks',
        table: {
          head: ['Days', 'What to do'],
          rows: [
            ['1–3', 'Let them lick a dab of pet toothpaste off your finger'],
            ['4–6', 'Rub your finger along the outside of the teeth and gums'],
            ['7–10', 'Swap to a finger brush; brush the back teeth gently'],
            ['11–14', 'Use the toothbrush at a 45° angle to the gum line, outside surfaces only'],
          ],
        },
        callout: { kind: 'tip', text: 'Focus on the big back teeth and the canines — that is where tartar builds fastest. The inner surfaces matter less.' },
      },
      {
        heading: 'If brushing is not possible',
        bullets: [
          'Vet-approved dental chews or a dental diet',
          'Water additives and dental gels, as a second best',
          'More frequent professional cleans',
        ],
      },
    ],
    faqs: [
      {
        q: 'My pet already has tartar — will brushing remove it?',
        a: 'No. Brushing stops new tartar forming; existing tartar needs a professional scale and clean first.',
      },
      {
        q: 'What if my pet’s gums bleed?',
        a: 'A little bleeding usually means gingivitis. Keep brushing gently and book a dental check to see how far it has gone.',
      },
    ],
  },
  {
    id: 'dental-abscess',
    title: 'Dental Abscess in Dogs and Cats: Swelling Under the Eye and Other Signs',
    dek: 'A swelling below the eye is often a tooth problem, not an eye problem. How tooth-root abscesses show up and how they are treated.',
    date: '2026-09-18',
    readMins: 5,
    tags: ['Dental', 'Dogs', 'Cats'],
    image: catYawn,
    serviceId: 'dental',
    sections: [
      {
        heading: 'Overview',
        body: [
          'An abscess forms when infection reaches the root of a tooth — through a fracture, a worn tooth or advanced gum disease. Pus builds up at the root tip with nowhere to drain, which is intensely painful.',
          'The large upper chewing tooth in dogs is the classic culprit: its roots sit just below the eye.',
        ],
      },
      {
        heading: 'Signs',
        bullets: [
          'A swelling on the face, often just below the eye',
          'A draining wound on the cheek or under the chin',
          'Dropping food, chewing on one side, or pawing at the mouth',
          'Bad breath, drooling, or not wanting the face touched',
        ],
        callout: {
          kind: 'warning',
          text: 'A facial swelling with fever or lethargy needs a vet the same day — the infection can spread.',
        },
      },
      {
        heading: 'Treatment',
        body: [
          'Antibiotics and pain relief settle the infection, but they do not remove its cause. Under anaesthesia, the vet X-rays the tooth and either extracts it or, for some important teeth, treats the root.',
        ],
        callout: { kind: 'tip', text: 'Do not let a pet chew on bones, antlers or hard nylon toys — they are the most common cause of the fractures that lead to abscesses.' },
      },
    ],
    faqs: [
      {
        q: 'Will antibiotics alone cure an abscess?',
        a: 'They usually bring the swelling down, but it comes back unless the infected tooth is treated or removed.',
      },
    ],
  },
  {
    id: 'tooth-extraction',
    title: 'Tooth Extraction in Dogs and Cats: When Is It Necessary?',
    dek: 'Pets manage very well with fewer teeth — and much better without painful ones. When a vet recommends taking a tooth out, and what recovery looks like.',
    date: '2026-09-15',
    readMins: 5,
    tags: ['Dental', 'Dogs', 'Cats'],
    image: dogYawn,
    serviceId: 'dental',
    sections: [
      {
        heading: 'When extraction is the right call',
        bullets: [
          'Advanced periodontal disease with a loose tooth',
          'A fractured tooth with the pulp exposed',
          'A tooth-root abscess',
          'Resorptive lesions in cats — painful holes in the tooth',
          'Baby teeth that did not fall out and crowd the adult ones',
        ],
      },
      {
        heading: 'What happens on the day',
        body: [
          'The pet is examined and usually has a pre-anaesthetic blood test. Under anaesthesia, the vet X-rays the mouth, numbs the area with a local block, removes the tooth — sectioning teeth with several roots — and closes the gum with dissolving stitches.',
        ],
        callout: { kind: 'tip', text: 'Most pets go home the same day and eat soft food that evening.' },
      },
      {
        heading: 'Recovery',
        table: {
          head: ['When', 'What to expect'],
          rows: [
            ['First 2–3 days', 'Soft food; pain relief as prescribed'],
            ['Up to 2 weeks', 'No hard chews or tug toys; stitches dissolve'],
            ['After 2 weeks', 'Recheck; back to normal food for most pets'],
          ],
        },
        callout: {
          kind: 'warning',
          text: 'Call the clinic if there is bleeding that does not stop, swelling that grows, or your pet will not eat after 24 hours.',
        },
      },
    ],
    faqs: [
      {
        q: 'Can my dog eat normally with missing teeth?',
        a: 'Yes. Dogs and cats swallow most food with little chewing, and they eat better once a painful tooth is gone.',
      },
    ],
  },
  {
    id: 'rabbit-teeth',
    title: 'Dental Disease in Rabbits and Small Pets: Signs and Vet Treatment',
    dek: 'Rabbit, guinea pig and chinchilla teeth grow all their lives. When they stop wearing down evenly, problems follow fast.',
    date: '2026-09-10',
    readMins: 4,
    tags: ['Dental', 'Prevention'],
    image: rabbit,
    serviceId: 'exotic-pets',
    sections: [
      {
        heading: 'Overview',
        body: [
          'A rabbit’s teeth grow two to three millimetres a week and are worn down by chewing hay. Without enough fibre, or with a misaligned jaw, they overgrow and form sharp spurs that cut the tongue and cheeks.',
        ],
      },
      {
        heading: 'Signs',
        bullets: [
          'Eating less, or picking out only soft foods',
          'Drooling or a wet chin',
          'Smaller or fewer droppings',
          'Weepy eyes or a lump along the jaw',
        ],
        callout: {
          kind: 'warning',
          text: 'A rabbit that has not eaten for 12 hours is an emergency — its gut can stop working.',
        },
      },
      {
        heading: 'Prevention',
        bullets: [
          'Unlimited hay — about 80% of the diet',
          'Fresh greens daily; pellets as a small extra only',
          'A dental check with an exotic-pet vet once or twice a year',
        ],
      },
    ],
    faqs: [
      {
        q: 'Can overgrown teeth be trimmed?',
        a: 'Yes — under sedation, with a dental burr. Clipping them with nail cutters can split the tooth and is not recommended.',
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
