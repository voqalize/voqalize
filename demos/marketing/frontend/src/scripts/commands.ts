/**
 * Hidden commands: things a visitor can ask the page itself to do, by voice
 * (the brain's `site_command`) or, with the simulated voice, by typing.
 * Dark or light, bigger or smaller, a phone-sized view on a desktop, and the
 * motion: pause, play, slower, faster, replay; and scrolling.
 */
import { replay, setPaused, setSpeed } from './motion';
import type { SiteCommand } from './actions.gen';

export type Command = SiteCommand['command'];

const root = document.documentElement;
const ZOOMS = [0.9, 1, 1.15, 1.3];
let zoom = 1;
let speed = 1;

function store(k: string, v: string | null) {
  try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* storage can be blocked */ }
}

export function setTheme(t: 'dark' | 'light') {
  root.dataset.theme = t;
  store('vq-theme', t);
  // A page shown beside Tanvi follows too.
  document.querySelectorAll<HTMLIFrameElement>('iframe.pageview').forEach((f) => {
    const d = f.contentDocument?.documentElement;
    if (d) d.dataset.theme = t;
  });
}

function setZoom(z: number) {
  zoom = z;
  document.body.style.setProperty('zoom', z === 1 ? '' : String(z));
}

function videos(play: boolean) {
  document.querySelectorAll<HTMLVideoElement>('video[data-autoplay]').forEach((v) => {
    const r = v.getBoundingClientRect();
    const onScreen = r.bottom > 0 && r.top < innerHeight && r.width > 0;
    if (play && onScreen) void v.play().catch(() => {});
    else v.pause();
  });
}

/* A phone-sized copy of the site, in a frame over the desktop page. The copy runs
   in Read mode with no call of its own; Tanvi keeps talking from this page. */
function phone(open: boolean) {
  let wrap = document.getElementById('phone-view');
  if (!open) { wrap?.remove(); document.body.classList.remove('has-phone-view'); return; }
  if (matchMedia('(max-width: 860px)').matches || wrap) return;
  wrap = document.createElement('div');
  wrap.id = 'phone-view';
  wrap.className = 'phone-view';
  wrap.innerHTML = `<div class="phone-view__device"><iframe title="Voqalize on a phone" src="/?mode=read&amp;embed=1${location.hash}"></iframe></div>
    <button type="button" class="phone-view__close">Back to desktop</button>`;
  wrap.querySelector('button')!.addEventListener('click', () => phone(false));
  document.body.append(wrap);
  document.body.classList.add('has-phone-view');
}

/* Scrolling: the open section's own scroll in Talk mode, the page in Read mode. */
function scroll(by: 'down' | 'up' | 'top') {
  // A page beside Tanvi scrolls inside its own frame.
  const framed = document.querySelector<HTMLIFrameElement>('[data-section="page"][data-active] iframe')?.contentWindow;
  const smooth0 = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  if (framed && document.body.dataset.mode === 'talk') {
    if (by === 'top') framed.scrollTo({ top: 0, behavior: smooth0 });
    else framed.scrollBy({ top: (by === 'down' ? 1 : -1) * framed.innerHeight * 0.7, behavior: smooth0 });
    return;
  }
  const panel = document.getElementById('panel');
  const talk = document.body.dataset.mode === 'talk' && document.getElementById('app')?.classList.contains('is-split');
  const box: Element | Window = talk && panel && panel.scrollHeight > panel.clientHeight + 4 ? panel : window;
  const h = box instanceof Window ? innerHeight : (box as HTMLElement).clientHeight;
  const smooth = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  if (by === 'top' && box === window && talk && panel) panel.scrollIntoView({ block: 'start', behavior: smooth });
  else if (by === 'top') box.scrollTo({ top: 0, behavior: smooth });
  else box.scrollBy({ top: (by === 'down' ? 1 : -1) * h * 0.7, behavior: smooth });
}

export function run(c: Command) {
  switch (c) {
    case 'dark': setTheme('dark'); return;
    case 'light': setTheme('light'); return;
    case 'bigger': setZoom(ZOOMS[Math.min(ZOOMS.length - 1, ZOOMS.indexOf(zoom) + 1)]); return;
    case 'smaller': setZoom(ZOOMS[Math.max(0, ZOOMS.indexOf(zoom) - 1)]); return;
    case 'normal_size': setZoom(1); return;
    case 'mobile': phone(true); return;
    case 'desktop': phone(false); return;
    case 'pause_motion': setPaused(true); videos(false); return;
    case 'play_motion': setPaused(false); videos(true); return;
    case 'slower': speed = Math.min(2.5, speed * 1.6); setSpeed(speed); return;
    case 'faster': speed = Math.max(0.4, speed / 1.6); setSpeed(speed); return;
    case 'replay': replay(); return;
    case 'scroll_down': scroll('down'); return;
    case 'scroll_up': scroll('up'); return;
    case 'scroll_top': scroll('top'); return;
  }
}

/** Typed phrases for the simulated voice. The live brain understands far more. */
const PHRASES: Array<[RegExp, Command]> = [
  [/dark/, 'dark'], [/light mode|too dark/, 'light'],
  [/bigger|larger|zoom in|can't read/, 'bigger'], [/smaller|zoom out/, 'smaller'], [/normal size|reset size/, 'normal_size'],
  [/mobile|phone view|on a phone/, 'mobile'], [/desktop/, 'desktop'],
  [/stop (the )?anim|pause|too much movement/, 'pause_motion'], [/start (the )?anim|play the anim|resume/, 'play_motion'],
  [/slow/, 'slower'], [/speed up|faster/, 'faster'], [/again|replay/, 'replay'],
  [/scroll down|show me more/, 'scroll_down'], [/scroll up/, 'scroll_up'], [/to the top|back up/, 'scroll_top'],
];
export function commandFor(text: string): Command | null {
  const t = text.toLowerCase();
  return PHRASES.find(([re]) => re.test(t))?.[1] ?? null;
}

// The theme a visitor chose last time, before first paint where possible.
try { const t = localStorage.getItem('vq-theme'); if (t === 'dark' || t === 'light') root.dataset.theme = t; } catch { /* ignore */ }
