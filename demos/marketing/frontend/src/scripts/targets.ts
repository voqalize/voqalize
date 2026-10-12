/**
 * Tanvi's hands inside a section: every control she can switch, open or point at.
 *
 * Each one is marked in the markup with `data-voice="<id>"`, the same id as in
 * `src/data/voice.json`, which the brain reads too. A target that is a button is
 * pressed, exactly as a visitor would press it (a tab opens and stays, a step plays
 * from there, rupees replace dollars); any other target is scrolled to and pointed
 * at. Either way it gets a short vermilion ring, so the visitor sees where to look.
 *
 * The visitor's own clicks on the same controls are reported back to the brain, so
 * she knows what is on screen. Her clicks are not.
 */
import voice from '../data/voice.json';

/** A control in a home section, or (`page` set) a part of another page, scrolled to beside Tanvi. */
export interface Target { id: string; section: string; does: string; page?: string; part?: string }
export interface Link { id: string; url: string; label: string; does: string }
export interface SitePage { id: string; url: string; title: string; does: string }
export const TARGETS: Target[] = [...voice.targets, ...voice.parts.map((x) => ({ id: x.id, section: '', does: x.does, page: x.page, part: x.part }))];
export const LINKS = voice.links as Link[];
/** The site's other pages Tanvi can open beside her (open_page). */
export const PAGES = voice.pages as SitePage[];
export const pageAt = (path: string) => PAGES.find((p) => p.url === path.replace(/\/$/, '') || p.url === path);

const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
let driving = false;

function press(el: HTMLElement) {
  driving = true;
  try { el.click(); } finally { driving = false; }
}

/** The element for a target, inside its section. */
export function targetEl(id: string): HTMLElement | null {
  const t = TARGETS.find((x) => x.id === id);
  if (!t) return null;
  return document.querySelector<HTMLElement>(`[data-section="${t.section}"] [data-voice="${id}"]`);
}

/** Carry out a target. `opened` is true when its section has only just been opened, so its
 *  motion has to settle (a loop restarts when it comes on screen) before a step is chosen. */
export function act(id: string, opened: boolean) {
  const run = () => {
    const el = targetEl(id);
    if (!el) return;
    // A step inside a tab that is not showing: open that tab first.
    const panel = el.closest<HTMLElement>('[role="tabpanel"]');
    if (panel?.hidden) {
      const tab = document.querySelector<HTMLElement>(`[role="tab"][aria-controls="${panel.id}"]`);
      if (tab) press(tab);
    }
    // A scene of the Read-mode carousel: slide to it with its own dot.
    const reel = el.closest<HTMLElement>('[data-reel]');
    if (reel && el.parentElement?.classList.contains('reel__track')) {
      const dot = reel.querySelectorAll<HTMLElement>('.reel__dots button')[[...el.parentElement.children].indexOf(el)];
      if (dot && dot.getClientRects().length) press(dot);
    }
    const button = el.matches('button, [role="tab"]');
    if (button) press(el);
    if (el.getClientRects().length) el.scrollIntoView({ block: button ? 'nearest' : 'center', behavior: reduced() ? 'auto' : 'smooth' });
    point(el);
  };
  if (opened) window.setTimeout(run, reduced() ? 0 : 520);
  else run();
}

function point(el: HTMLElement) {
  el.classList.remove('is-pointed');
  void el.offsetWidth;
  el.classList.add('is-pointed');
  window.setTimeout(() => el.classList.remove('is-pointed'), 2600);
}

/** Report the visitor's own presses on a voice control. */
export function onVisitorControl(report: (id: string) => void) {
  document.addEventListener('click', (e) => {
    if (driving || !e.isTrusted) return;
    const el = (e.target as Element).closest<HTMLElement>('[data-voice]');
    if (!el || !el.matches('button, [role="tab"]')) return;
    report(el.dataset.voice!);
  });
}
