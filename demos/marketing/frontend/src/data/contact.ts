/**
 * Press and contact page data: where messages go, and the press kit files that exist in public/.
 */
export const CONTACT_EMAIL = 'support@voqalize.com';
/** Samkeet's booking page (cal.id): anyone picks a free slot for a demo or a talk. Always a new tab. */
export const BOOK_URL = 'https://cal.id/samkeet-jain';

export interface KitFile { name: string; file: string; small: string; format: string; size: string; ground: 'light' | 'dark' }
export const logos: KitFile[] = [
  // Full size from marketing/brand-kit/logos (2172 × 724), with the site's 900 × 300 copies in public/brand.
  { name: 'Logo for light backgrounds', file: '/contact/voqalize-logo-light.png', small: '/brand/logo-light.png', format: 'PNG, transparent', size: '2172 × 724', ground: 'light' },
  { name: 'Logo for dark backgrounds', file: '/contact/voqalize-logo-dark.png', small: '/brand/logo-dark.png', format: 'PNG, transparent', size: '2172 × 724', ground: 'dark' },
];

/** App icons from marketing/brand-kit/icons: rounded tiles (22% corners) and one full-bleed square. */
export interface IconFile { name: string; file: string; small: string; size: string }
export const icons: IconFile[] = [
  { name: 'App icon, dark', file: '/contact/voqalize-icon-dark.png', small: '/contact/voqalize-icon-dark-256.png', size: '1024 × 1024' },
  { name: 'App icon, light', file: '/contact/voqalize-icon-light.png', small: '/contact/voqalize-icon-light-256.png', size: '1024 × 1024' },
  { name: 'App icon, gradient', file: '/contact/voqalize-icon-gradient.png', small: '/contact/voqalize-icon-gradient-256.png', size: '1024 × 1024' },
  { name: 'App icon, square (for stores that round corners)', file: '/contact/voqalize-icon-dark-512-square.png', small: '/contact/voqalize-icon-dark-square-256.png', size: '512 × 512' },
];

/** Every character still in public/characters (the home page cast plus Ira). */
export const characters = ['tanvi', 'tara', 'tushar', 'tanya', 'tess', 'trisha', 'ira'];
