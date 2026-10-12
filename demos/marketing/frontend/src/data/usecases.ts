/**
 * Use cases: six everyday apps, before and with Voqalize. Example apps and numbers,
 * labelled as such on the page. Each tab plays one loop in its own drawn app
 * (src/components/usecases/*.astro): the app idles, the person says the line
 * (step 1), the app does the work, and the agent replies on the last step.
 */
export interface UseCase {
  id: 'jewelry' | 'banking' | 'forms' | 'contracts' | 'cab' | 'food';
  tab: string;
  /** The example app's name, shown in its title bar. */
  app: string;
  said: string;
  today: string;
  /** What the app does with that one sentence (the "With Voqalize" line). */
  with: string;
  reply: string;
  /** Step durations in ms for the motion loop (motion.ts). Step 1 is the person
   *  speaking; the last step is the agent's reply. Around 8 to 11 s in all. */
  steps: number[];
}

export const USE_CASES: UseCase[] = [
  {
    id: 'jewelry', tab: 'Jewelry store', app: 'Aurum Jewels',
    said: 'Gold earrings under $800 that go with a green dress.',
    today: 'Seven filters and some guessing.',
    with: 'One sentence. The shop narrows to two pairs and says why.',
    reply: 'These two go with green. The hoops are $640.',
    steps: [1500, 2200, 1000, 1100, 3400],
  },
  {
    id: 'banking', tab: 'Banking', app: 'Tidewell Bank',
    said: 'I want to buy a car. How much loan would I need, and which offer is cheapest?',
    today: 'Four screens and a spreadsheet.',
    with: 'One question. The app works out the loan and ranks the offers.',
    reply: 'About $18,000. The credit union offer is the cheapest.',
    steps: [1300, 2600, 1300, 1000, 900, 3300],
  },
  {
    id: 'forms', tab: 'Long forms', app: 'Change of address',
    said: 'My address is 14 Elm Street, apartment 3B, Austin, 78701.',
    today: 'Fourteen fields and a list of fifty states.',
    with: 'One sentence. The form finds the right fields and fills them, Texas included.',
    reply: 'Got it. Austin, Texas?',
    steps: [1100, 2400, 900, 600, 600, 1200, 800, 3000],
  },
  {
    id: 'contracts', tab: 'Contracts', app: 'Supply agreement',
    said: 'Which clauses here would worry a buyer?',
    today: 'Forty pages and a highlighter.',
    with: 'One question. It jumps to the three clauses and marks each one.',
    reply: 'Three. I have marked each one.',
    steps: [1700, 1900, 800, 700, 700, 700, 3100],
  },
  {
    id: 'cab', tab: 'Cab booking', app: 'Ride',
    said: 'Get me a ride to the airport. Something bigger, we have four bags.',
    today: 'Pickup, drop-off, car type, luggage, confirm.',
    with: 'One sentence. Airport set, route drawn, an XL picked for the bags.',
    reply: 'An XL is six minutes away. Book it?',
    steps: [1200, 2400, 900, 1300, 900, 900, 3000],
  },
  {
    id: 'food', tab: 'Food delivery', app: 'Order in',
    said: 'Reorder Friday’s pizza, but a large, and no olives.',
    today: 'Orders, reorder, size, toppings, checkout.',
    with: 'One sentence. Friday’s pizza, resized, olives off, ready to place.',
    reply: 'Large, no olives, same address. Place it?',
    steps: [1300, 2300, 1000, 900, 1000, 700, 3000],
  },
];
