/**
 * Cookie consent: what the visitor has allowed, and a way for tags to wait for it.
 *
 * Three categories. Necessary cookies (the site working, the theme, this choice) are
 * always on. Analytics (PostHog, Google Analytics) and advertising load only after the
 * visitor allows them. The choice lives in localStorage under `vq-consent`; bumping
 * VERSION asks everyone again (do that when a new kind of cookie is added).
 *
 * Adding a tag later: `onAllowed('analytics', () => { load PostHog or GA here })`. It runs
 * at once if already allowed, or the moment the visitor allows it. Google tags also see
 * Consent Mode updates (defaults are set to denied in Base.astro before any tag loads).
 *
 * Global Privacy Control (navigator.globalPrivacyControl) is an opt-out of advertising:
 * with it on, "Accept all" leaves advertising off; only switching it on in Customize
 * turns it on. The privacy policy (sections 8 and 15) promises this.
 */
export type Category = 'analytics' | 'ads';
export interface Consent { v: number; analytics: boolean; ads: boolean; at: string }

const KEY = 'vq-consent';
const VERSION = 1;

export const gpc = (): boolean => (navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl === true;

export function read(): Consent | null {
  try {
    const c = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Consent | null;
    return c && c.v === VERSION ? c : null;
  } catch { return null; }
}

export function allowed(cat: Category): boolean {
  return read()?.[cat] === true;
}

type GtagFn = (...args: unknown[]) => void;
function tellGoogle(c: Consent) {
  const gtag = (window as unknown as { gtag?: GtagFn }).gtag;
  if (!gtag) return;
  const v = (on: boolean) => (on ? 'granted' : 'denied');
  gtag('consent', 'update', {
    analytics_storage: v(c.analytics),
    ad_storage: v(c.ads), ad_user_data: v(c.ads), ad_personalization: v(c.ads),
  });
}

export function save(choice: { analytics: boolean; ads: boolean }): Consent {
  const c: Consent = { v: VERSION, analytics: choice.analytics, ads: choice.ads, at: new Date().toISOString() };
  try { localStorage.setItem(KEY, JSON.stringify(c)); } catch { /* private mode: the choice lasts this page only */ }
  tellGoogle(c);
  window.dispatchEvent(new CustomEvent<Consent>('vq:consent', { detail: c }));
  return c;
}

/** Run `fn` once, as soon as `cat` is allowed (now, or when the visitor allows it). */
export function onAllowed(cat: Category, fn: () => void) {
  if (allowed(cat)) { fn(); return; }
  const on = (e: Event) => {
    if (!(e as CustomEvent<Consent>).detail[cat]) return;
    window.removeEventListener('vq:consent', on);
    fn();
  };
  window.addEventListener('vq:consent', on);
}

// For tag snippets pasted into the page later.
(window as unknown as { vqConsent: object }).vqConsent = { allowed, onAllowed, read };
