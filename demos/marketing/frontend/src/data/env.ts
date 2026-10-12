/**
 * Which Voqalize environment the site points at. Local and dev builds use dev; a
 * production build sets PUBLIC_VOQALIZE_ENV=prod. Every Console link carries
 * `data-console`, and Base.astro corrects those links by hostname at load
 * (voqalize.com goes to prod; localhost and *.dev.voqalize.com go to dev), so a
 * missed build flag never sends a visitor to the wrong console.
 */
export const CONSOLE_URLS = { dev: 'https://app.dev.voqalize.com', prod: 'https://app.voqalize.com' } as const;
export const VOQALIZE_ENV: keyof typeof CONSOLE_URLS = import.meta.env.PUBLIC_VOQALIZE_ENV === 'prod' ? 'prod' : 'dev';
export const CONSOLE_URL = CONSOLE_URLS[VOQALIZE_ENV];
