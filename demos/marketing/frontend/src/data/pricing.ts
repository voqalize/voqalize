/**
 * Every price the site quotes, in one file. Copied from the current voqalize.com
 * (platform/frontend/apps/marketing/src/data/pricing.ts) on 2026-10-11, as Samkeet
 * asked. Changed since: the free signup credit is 300 conversation minutes, plans cap the number of
 * applications, and annual billing (ten months for twelve, as on the current site) is the default view.
 * Plug & Play and developer integration will be priced apart later (docs/sections/pricing.md).
 */
export type Currency = 'usd' | 'inr';
export type Money = Record<Currency, number>;

export const CURRENCIES = [
  { k: 'usd', label: 'USD', tax: 'Prices exclude tax.' },
  { k: 'inr', label: 'INR', tax: 'Prices exclude GST.' },
] as const;

export const SIGNUP_MINUTES = 300;

/** Annual is invoiced as ten months for twelve (current site). */
export const ANNUAL = { monthsPaid: 10, monthsBilled: 12 };

/** The annual invoice for a plan, and the monthly figure it works out to. */
export function annual(price: Money, c: Currency) {
  const total = price[c] * ANNUAL.monthsPaid;
  return { total, perMonth: total / ANNUAL.monthsBilled };
}

export interface Plan {
  k: string;
  name: string;
  who: string;
  /** Monthly fee; null where it is quoted. */
  price: Money | null;
  rate: Money | null;
  minutes: number | null;
  signupMinutes?: number;
  concurrency: number | null;
  storageGb: number | null;
  inherits?: string;
  items: readonly string[];
  cta: string;
  recommended?: boolean;
}

export const PLANS: readonly Plan[] = [
  {
    k: 'free', name: 'Free', who: 'Build against the real thing.',
    price: { usd: 0, inr: 0 }, rate: null, minutes: null, signupMinutes: SIGNUP_MINUTES,
    concurrency: 1, storageGb: 1,
    items: ['Up to one application', 'Every feature, ungated', 'Docs, SDKs, MCP and the demos'],
    cta: 'Start free',
  },
  {
    k: 'starter', name: 'Starter', who: 'One workflow in production.',
    price: { usd: 99, inr: 9999 }, rate: { usd: 0.03, inr: 2.7 }, minutes: 3000,
    concurrency: 5, storageGb: 10,
    items: ['Up to two applications', 'Email support, next business day'],
    cta: 'Choose Starter',
  },
  {
    k: 'growth', name: 'Growth', who: 'Several workflows, or one that peaks.',
    price: { usd: 499, inr: 49999 }, rate: { usd: 0.027, inr: 2.43 }, minutes: 18000,
    concurrency: 25, storageGb: 25, inherits: 'Starter',
    items: ['Up to five applications', 'Your custom character', 'Your custom voice', 'Forward Deployed Engineer for tech support', 'Priority support in a shared Slack channel', '99.5% uptime SLA'],
    cta: 'Choose Growth', recommended: true,
  },
  {
    k: 'enterprise', name: 'Enterprise', who: 'Voice is load bearing.',
    price: null, rate: null, minutes: null, concurrency: null, storageGb: null, inherits: 'Growth',
    items: ['Speech models deployed in your VPC', 'SSO, DPA and a 99.9% uptime SLA', 'Named account manager', 'Bring your own TTS and STT'],
    cta: 'Talk to us',
  },
];

/** What a conversation minute carries. */
export const INCLUDED = [
  { t: 'WebRTC transport', d: 'Media direct to the node.' },
  { t: 'Speech-to-text', d: 'Our models, on our own GPUs.' },
  { t: 'Text-to-speech', d: 'Switchable mid-session.' },
  { t: 'Turn-taking', d: 'Voice activity, endpointing and interruption handling.' },
  { t: 'The character', d: 'Faces that listen, react and lip-sync, on the device.' },
  { t: 'Observability', d: 'Session logs, transcripts and per-turn timings.' },
  { t: 'Network', d: 'Egress and bandwidth.' },
] as const;

export const ADDITIONAL = [
  { t: 'Storage', unit: 'per GB a month, above your plan’s quota', price: { usd: 0.06, inr: 5.4 } },
  { t: 'Recording', unit: 'per recorded minute, only when you record', price: { usd: 0.004, inr: 0.36 } },
] as const;

export const QA = [
  { q: 'What is a billable minute?', a: 'Audio connect to session end, counted by the second and totalled monthly.' },
  { q: 'Is the LLM included?', a: 'With Plug & Play, yes: we run the AI and it is in the minute. With developer integration, your agent runs in your backend on your own model account, and those tokens bill you there.' },
  { q: 'Are speech-to-text and text-to-speech billed separately?', a: 'No. We run both models ourselves and both are in the minute, on every plan.' },
  { q: 'What about recording and storage?', a: 'Both are metered on top of the minute: recording per recorded minute, storage per GB a month above your plan’s quota.' },
  { q: 'What happens past my included minutes?', a: 'Sessions keep connecting. Every further minute bills at your plan’s rate.' },
  { q: 'Do unused minutes carry over?', a: 'No. The block resets at the start of each month.' },
  { q: 'What happens at my concurrency limit?', a: 'The next session is refused with a named error your code can catch. Email us and we raise the ceiling.' },
  { q: 'Can I change plans mid-cycle?', a: 'Upgrades apply immediately and are prorated. Downgrades apply at renewal.' },
  { q: 'Can I pay in rupees?', a: 'Yes. Indian customers are invoiced in rupees, plus GST.' },
  { q: 'Does Voqalize do telephony?', a: 'No. Voqalize runs in a browser or a mobile app, next to the screen the user is already on.' },
  { q: 'Can the speech models run in my VPC?', a: 'Yes. That is an enterprise deployment. Talk to us and we will scope it.' },
] as const;

export { CONSOLE_URL } from './env';
export { BOOK_URL as CONTACT_URL } from './contact';

export function money(c: Currency, v: number): string {
  const sym = c === 'usd' ? '$' : '₹';
  if (v === 0) return `${sym}0`;
  if (v < 1) return sym + v.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
  const r = c === 'inr' && v >= 100 ? Math.round(v) : Math.round(v * 100) / 100;
  const dec = Number.isInteger(r) ? 0 : 2;
  return sym + r.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

export const count = (n: number) => n.toLocaleString('en-US');
