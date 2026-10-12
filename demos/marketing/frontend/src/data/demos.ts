/**
 * The Experience Center: today's working demos, copied from the current voqalize.com
 * (platform/frontend/apps/marketing/src/data/demos.ts) on 2026-10-11. Each opens in a
 * new tab at voqalize.com/demos/<name>/. Samkeet adds demos over time; add one here
 * with a screenshot in public/shots.
 */
export const DEMO_BASE = 'https://voqalize.com/demos';

export interface Demo { name: string; tag: string; title: string; blurb: string; shot: string }

export const DEMOS: Demo[] = [
  { name: 'aura', tag: 'Banking', title: 'Answer a question inside the app', shot: 'aura-call.webp',
    blurb: 'A customer asks the bank a question out loud. The agent opens the page the answer lives on, signs them in when it needs their account, and explains it against what is on screen.' },
  { name: 'servicing', tag: 'Mortgage servicing', title: 'Work up a case at the console', shot: 'servicing-queue.webp',
    blurb: 'A servicing agent talks through a case. The copilot pulls the record, reconciles the numbers, catches the blocker on a regulated step and drafts the change, then stops for the human.' },
  { name: 'orderdesk', tag: 'Pharma distribution', title: 'Take a bulk order by voice', shot: 'orderdesk-scenarios.webp',
    blurb: 'A pharmacist reels off a morning order in Hindi. Every line lands on screen and resolves against a real catalog; where a name is ambiguous, they pick from products instead of answering a question.' },
  { name: 'legal', tag: 'Legal', title: 'Review a contract out loud', shot: 'legal-msa.webp',
    blurb: 'In-house counsel reads a vendor agreement and talks through it. The agent marks the clauses and obligations on screen as they read, in the document they are already in.' },
  { name: 'sugar', tag: 'Healthcare', title: 'Run a daily check-in', shot: 'sugar-console.webp',
    blurb: 'A diabetes check-in that starts from a phone notification. "Curd rice and two rotis" becomes a logged meal, and anything clinical goes to a human.' },
  { name: 'travel', tag: 'Travel', title: 'Plan a trip in one pass', shot: 'travel-home.webp',
    blurb: 'Dates, cities and budget in one breath. The itinerary fills in on screen while flights and hotels are searched in the background.' },
];
