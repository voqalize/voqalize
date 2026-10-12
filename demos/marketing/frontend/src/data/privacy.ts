/**
 * Tables of contents for the two legal pages (/privacy and /dpa). The section ids here are the
 * anchors the components render, so a link to /privacy#t-liability or /dpa#annex-2 keeps working.
 * Keep each list in the same order as its document; the build check in docs/sections/page-legal.md
 * confirms every id resolves.
 */
export interface TocItem { id: string; n: string; title: string }
export interface TocGroup { id: string; label: string; items: TocItem[] }

/** The date shown on both pages (founder, 2026-10-12). */
export const LEGAL_UPDATED = '12 October 2026';

export const PRIVACY_TOC: TocGroup[] = [
  {
    id: 'privacy-policy',
    label: 'Part A. Privacy policy',
    items: [
      { id: 'who-we-are', n: '1', title: 'Who we are and what this covers' },
      { id: 'roles', n: '2', title: 'Our two roles: controller and processor' },
      { id: 'collect', n: '3', title: 'Information we collect as controller' },
      { id: 'voice-data', n: '4', title: 'Voice data we process for our customers' },
      { id: 'sensitive', n: '5', title: 'Voice, biometrics and sensitive data' },
      { id: 'use', n: '6', title: 'How we use information' },
      { id: 'bases', n: '7', title: 'Legal bases for processing' },
      { id: 'share', n: '8', title: 'How we share information' },
      { id: 'transfers', n: '9', title: 'Where data is processed' },
      { id: 'retention', n: '10', title: 'How long we keep data' },
      { id: 'deletion', n: '11', title: 'Deletion' },
      { id: 'security', n: '12', title: 'Security' },
      { id: 'children', n: '13', title: 'Children' },
      { id: 'rights', n: '14', title: 'Your rights' },
      { id: 'cookies', n: '15', title: 'Cookies and browser storage' },
      { id: 'changes', n: '16', title: 'Changes to this policy' },
      { id: 'contact', n: '17', title: 'Contact and grievance officer' },
    ],
  },
  {
    id: 'terms',
    label: 'Part B. Terms of service',
    items: [
      { id: 't-agreement', n: '1', title: 'Agreement to these terms' },
      { id: 't-services', n: '2', title: 'Our services' },
      { id: 't-accounts', n: '3', title: 'Accounts, API keys and eligibility' },
      { id: 't-payment', n: '4', title: 'Plans, purchases and payment' },
      { id: 't-ip', n: '5', title: 'Intellectual property' },
      { id: 't-content', n: '6', title: 'Your content and feedback' },
      { id: 't-voice', n: '7', title: 'Your duties when you deploy voice' },
      { id: 't-prohibited', n: '8', title: 'Prohibited activities' },
      { id: 't-ai', n: '9', title: 'AI output, characters and your brain' },
      { id: 't-third', n: '10', title: 'Third-party services' },
      { id: 't-management', n: '11', title: 'Services management' },
      { id: 't-privacy', n: '12', title: 'Privacy and data protection' },
      { id: 't-availability', n: '13', title: 'Changes, interruptions and service levels' },
      { id: 't-termination', n: '14', title: 'Term and termination' },
      { id: 't-law', n: '15', title: 'Governing law' },
      { id: 't-disputes', n: '16', title: 'Dispute resolution' },
      { id: 't-corrections', n: '17', title: 'Corrections' },
      { id: 't-disclaimer', n: '18', title: 'Disclaimer' },
      { id: 't-liability', n: '19', title: 'Limitation of liability' },
      { id: 't-indemnity', n: '20', title: 'Indemnification' },
      { id: 't-data', n: '21', title: 'User data' },
      { id: 't-electronic', n: '22', title: 'Electronic communications and signatures' },
      { id: 't-misc', n: '23', title: 'Miscellaneous' },
      { id: 't-contact', n: '24', title: 'Contact us' },
    ],
  },
];

export const DPA_TOC: TocGroup[] = [
  {
    id: 'addendum',
    label: 'Addendum',
    items: [
      { id: 'd-definitions', n: '1', title: 'Definitions' },
      { id: 'd-scope', n: '2', title: 'Scope of this addendum' },
      { id: 'd-roles', n: '3', title: 'Roles of the parties' },
      { id: 'd-purpose', n: '4', title: 'Description and purpose of processing' },
      { id: 'd-terms', n: '5', title: 'Data processing terms' },
      { id: 'd-voice', n: '6', title: 'Voice, recordings and models' },
      { id: 'd-warranties', n: '7', title: 'Warranties' },
      { id: 'd-transfers', n: '8', title: 'Restricted transfers' },
      { id: 'd-precedence', n: '9', title: 'Precedence' },
      { id: 'd-indemnity', n: '10', title: 'Indemnity' },
      { id: 'd-severability', n: '11', title: 'Severability' },
      { id: 'd-misc', n: '12', title: 'Miscellaneous' },
    ],
  },
  {
    id: 'annexes',
    label: 'Annexes',
    items: [
      { id: 'annex-1', n: 'A1', title: 'Description of processing' },
      { id: 'annex-1-security', n: 'A1.4', title: 'Technical and organisational measures' },
      { id: 'annex-2', n: 'A2', title: 'Sub-processors' },
    ],
  },
];
