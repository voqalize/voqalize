/** Footer pages beyond the home page and the solutions. Each has its own file in src/pages/. */
export interface RoomDef { slug: string; title: string; group: 'Company' | 'Resources' }

export const ROOMS: RoomDef[] = [
  { slug: 'about', title: 'About', group: 'Company' },
  { slug: 'story', title: 'Our story', group: 'Company' },
  { slug: 'contact', title: 'Press and contact', group: 'Company' },
  { slug: 'security', title: 'Security and trust', group: 'Resources' },
  { slug: 'privacy', title: 'Privacy and terms', group: 'Resources' },
  { slug: 'dpa', title: 'Data processing addendum', group: 'Resources' },
];
