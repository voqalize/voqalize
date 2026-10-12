// Copy for the Security and trust page (/security). Notes and sources for every line:
// docs/sections/page-security.md. Practice claims come from the platform docs and the
// control plane; the four standards are the founder's statement (2026-10-11).

export interface Standard {
  id: string;
  /** The short mark drawn in the badge. */
  mark: string;
  /** Small line above the mark, inside the badge. */
  over: string;
  /** Small line under the mark, inside the badge. */
  under: string;
  /** The word set along the top of the ring. */
  ring: string;
  /** 'seal' for an audited certificate or report; 'law' (a plain tile) for a law, which issues no certificate. */
  kind: 'seal' | 'law';
  status: string;
  name: string;
  meaning: string;
}

export const STANDARDS: Standard[] = [
  {
    id: 'iso',
    mark: '27001',
    over: 'ISO/IEC',
    under: '2022',
    ring: 'CERTIFIED',
    kind: 'seal',
    status: 'Certified',
    name: 'ISO/IEC 27001:2022',
    meaning: 'How we run information security, from who gets access to how we handle an incident, audited by an independent certification body.',
  },
  {
    id: 'soc2',
    mark: 'SOC 2',
    over: 'Service org.',
    under: 'Controls',
    ring: 'COMPLIANT',
    kind: 'seal',
    status: 'Certified',
    name: 'SOC 2',
    meaning: 'The controls that keep customer data secure, examined by an independent auditor.',
  },
  {
    id: 'gdpr',
    mark: 'GDPR',
    over: 'European',
    under: 'Union',
    ring: 'COMPLIANT',
    kind: 'law',
    status: 'Certified',
    name: 'GDPR',
    meaning: 'The European Union’s rules for personal data, including each person’s right to see and delete what is held about them.',
  },
  {
    id: 'dpdp',
    mark: 'DPDP',
    over: 'India',
    under: 'Act 2023',
    ring: 'COMPLIANT',
    kind: 'law',
    status: 'Certified',
    name: 'DPDP Act, 2023',
    meaning: 'India’s data protection law. It asks for consent for a stated purpose, and gives people rights over their data.',
  },
];

/** The four principles: one line each. The ledger below them has the detail. */
export const PRINCIPLES = [
  {
    title: 'Recording starts switched off.',
    body: 'No audio is saved unless you turn recording on, for an agent or for a single call.',
  },
  {
    title: 'Encrypted on the way.',
    body: 'Voice travels over WebRTC, which encrypts every call with DTLS‑SRTP. There is no unencrypted mode to fall back to.',
  },
  {
    title: 'Your agent stays yours.',
    body: 'If you bring your own AI agent, its prompts, model, tools and conversation memory stay on your servers. We carry the words there and back.',
  },
  {
    title: 'Each part gets only what it needs.',
    body: 'The servers that carry voice hold no storage credentials, and the keys you create are kept only as a hash.',
  },
];

/** The ledger: everything a call touches, and what happens to it. */
export const LEDGER = [
  {
    what: 'Voice',
    detail: 'Carried between your customer’s device and our servers over WebRTC, encrypted with DTLS‑SRTP. Speech recognition and the agent’s voice run on speech servers we operate, so no outside speech company hears your customers. Audio is saved only when recording is on.',
  },
  {
    what: 'Camera and screen',
    detail: 'Only when your app turns them on. Carried the same way as voice, and saved only when recording is on.',
  },
  {
    what: 'Transcripts',
    detail: 'What your customer said and what your agent answered. They go to your AI agent with a signed token for that one session, so your agent can check the call came from us. We keep the session’s turns so you can review the call in the Console.',
  },
  {
    what: 'Recordings',
    detail: 'Off by default. You can turn them on for an agent or for one call, and each call records which setting turned recording on, so you can still tell after you change the default. The upload goes through a signed link that can write that one file and nothing else.',
  },
  {
    what: 'The character',
    detail: 'Drawn on your customer’s device from short cues such as listening, thinking and speaking. There is no video of the character to store.',
  },
  {
    what: 'Keys and access',
    detail: 'Secret keys are shown once, and we store only a hash of them. Browser keys work only from the websites you list. Teammates are owners, admins or members, and changes to your account go into an audit log.',
  },
  {
    what: 'How long we keep it',
    detail: 'Session data is kept for 30 days, then deleted. The demos on voqalize.com are never recorded.',
  },
  {
    what: 'Where it runs',
    detail: 'Every Voqalize service runs on Google Cloud in the Mumbai region, and nowhere else.',
  },
  {
    what: 'Model training',
    detail: 'We never use your customers’ audio, video, transcripts or recordings to train or improve speech or language models.',
  },
];
