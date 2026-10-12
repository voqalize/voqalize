/**
 * The shell: Talk and Read modes over one DOM.
 *
 * Read mode is the plain page: every section stacked, Tanvi docked as a pill.
 * Talk mode is a conversation. Before a section is open, Tanvi stands centre stage.
 * Once one is open, the screen splits: Tanvi, her words and what you said stay fixed
 * in a narrow left column, and the section fills the right side with its own scroll.
 * Sections are the same elements in both modes, never copies.
 *
 * Nothing in Talk mode is meant to be clicked during a conversation. The visitor
 * speaks; the brain in `../backend` moves the page through actions. With no browser keys
 * set (`.env.local`), a simulated voice stands in, and only then are the hints
 * clickable, so the site stays explorable in development.
 */
import { SECTIONS, routeSection, type SectionDef } from '../data/sections';
import { unhandledUiAction, type OpenPage, type OpenSection, type Show, type UiAction, type Viewing } from './actions.gen';
import { commandFor, run as runCommand } from './commands';
import { mountMotion } from './motion';
import { hasLiveCall, prepare, provisioned, startCall, type LiveCall } from './live';
import { attend, remember, track, trackError } from './analytics';
import { mountRibbon } from './ribbon';
import { LINKS, PAGES, TARGETS, act, onVisitorControl, pageAt } from './targets';
import { SimulatedVoice, type VoiceState } from './voice';
import { snapshot, watchViewing } from './viewing';

type Mode = 'talk' | 'read';
type SectionId = OpenSection['section'];
const $ = <T extends Element = HTMLElement>(s: string, r: ParentNode = document) => r.querySelector(s) as T;
const $$ = <T extends Element = HTMLElement>(s: string, r: ParentNode = document) => [...r.querySelectorAll(s)] as T[];
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const narrow = () => matchMedia('(max-width: 860px)').matches;

const body = document.body;
const app = $('#app');
const caption = $('#caption');
const you = $('#you');
const muteBtn = $<HTMLButtonElement>('#mute');
const face = $('#face');
const note = $('#hero-note');
const savedEl = $('#saved');
const hintsEl = $('#hints');
const linkCard = $<HTMLAnchorElement>('#linkcard');
const pageView = $<HTMLIFrameElement>('#pageview');
let pageId: string | null = null;
// The hero's opening line, kept so ending a call can put the page back as it first was.
const introHTML = caption.innerHTML;
const sim = new SimulatedVoice();
const ribbon = mountRibbon($<HTMLCanvasElement>('#ribbon'), 8);
const readRibbon = $<HTMLCanvasElement>('#ribbon-read');
if (readRibbon) mountRibbon(readRibbon, 9);

const visited = new Set<string>();
let saved = 0;
let active: string | null = null;
let started = false;
let live: LiveCall | null = null;
let connecting = false;
// For analytics: when the call started, whether it has connected, and who ended it.
let callT0 = 0;
let callUp = false;
let endedBy: 'visitor' | 'read_mode' | 'tanvi' | 'dropped' = 'dropped';
let stopViewing: (() => void) | null = null;
const viewSource = { active: () => active, frame: pageView };

/* ---------- voice state ---------- */
// No words for her state: the ring and the ribbon show it.
function setState(s: VoiceState) {
  body.dataset.voice = s;
  face.classList.toggle('is-listening', s === 'listening');
  ribbon.set(s === 'speaking' ? 22 : s === 'listening' ? 11 : 8);
}
sim.onState(setState);

/** Simulated voice only: the live brain speaks for itself. */
function speak(text: string): Promise<void> {
  if (live) return Promise.resolve();
  const spans = setCaption(text);
  return sim
    .say(text, (i) => { spans[i - 1]?.classList.remove('now'); spans[i]?.classList.add('on', 'now'); ribbon.pulse(); })
    .then(() => spans.forEach((s) => { s.classList.add('on'); s.classList.remove('now'); }));
}

function setCaption(text: string): HTMLSpanElement[] {
  caption.classList.remove('intro');
  caption.textContent = '';
  return text.split(/\s+/).filter(Boolean).map((w) => appendWord(w, false));
}

function appendWord(w: string, on: boolean): HTMLSpanElement {
  const s = document.createElement('span');
  s.className = on ? 'w on' : 'w';
  s.textContent = w;
  caption.append(s, ' ');
  return s;
}

function heard(text: string) {
  you.textContent = '';
  if (!text) return;
  const b = document.createElement('b');
  b.textContent = text;
  you.append('You said ', b);
}

/* ---------- modes ---------- */
function setMode(m: Mode, opts: { scroll?: boolean; fromBrain?: boolean } = {}) {
  const from = body.dataset.mode;
  const changed = from !== m;
  body.dataset.mode = m;
  if (changed) {
    remember({ site_mode: m });
    // Not the first paint choosing the remembered mode: only a real switch counts.
    if (body.classList.contains('is-ready')) track('mode_changed', { from, to: m, by: opts.fromBrain ? 'tanvi' : 'visitor' });
    // Talk mode: the open section holds the screen. Read mode: the one in the middle (analytics.ts).
    attend(m === 'talk' ? attended() : null);
  }
  $$('[data-set-mode]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.setMode === m)));
  try { localStorage.setItem('vq-mode', m); } catch { /* storage can be blocked */ }
  if (opts.scroll !== false) window.scrollTo({ top: 0 });
  // Read mode is the visitor choosing to read: the conversation ends, and the
  // docked Tanvi offers to start a new one.
  if (changed && live && m === 'read' && !opts.fromBrain) { endedBy = 'read_mode'; live.hangUp(); }
}

/* ---------- opening sections (Talk mode) ---------- */
function transition(fn: () => void) {
  type VT = { ready: Promise<void>; finished: Promise<void>; updateCallbackDone: Promise<void> };
  const d = document as Document & { startViewTransition?: (cb: () => void) => VT };
  if (reduced() || !d.startViewTransition) { fn(); return; }
  // Tanvi can move the page twice in a breath (open, then point; open, then close). A new
  // transition skips the one still running, which rejects its promises: expected, not an error.
  const t = d.startViewTransition(fn);
  for (const p of [t.ready, t.finished, t.updateCallbackDone]) p.catch(() => {});
}

function show(id: string | null) {
  $$('[data-section]').forEach((s) => s.toggleAttribute('data-active', s.dataset.section === id));
  app.classList.toggle('is-split', Boolean(id));
  active = id;
  $('#panel').scrollTop = 0;
  saveState();
  attend(attended());
}

/** What holds the screen in Talk mode, for analytics: the open section, or the page beside Tanvi. */
function attended(): string | null {
  return active === 'page' ? (pageId ? `page:${pageId}` : null) : active;
}

interface OpenOpts { said?: string; fromBrain?: boolean }

function openSection(id: string, opts: OpenOpts = {}) {
  const s = SECTIONS.find((x) => x.id === id);
  if (!s) return;
  if (active !== id) track('section_opened', { section: id, by: opts.fromBrain ? 'tanvi' : 'visitor', in_call: Boolean(live) });
  if (body.dataset.mode !== 'talk') setMode('talk', { fromBrain: opts.fromBrain });
  start();
  if (!visited.has(id)) { visited.add(id); saved += s.clicks; countTo(saved); }
  const next = SECTIONS[(SECTIONS.indexOf(s) + 1) % SECTIONS.length];

  if (live) {
    // A section opened from the nav or a link during a call: show it and tell Tanvi.
    if (!opts.fromBrain) live.event({ event: 'section_opened', payload: { section: id as SectionId } });
    if (active !== id) reveal(id);
    renderHints(next.id);
    return;
  }
  // Keys set but no call yet (say, the header's Experience Center): show it, say nothing.
  if (provisioned) { if (active !== id) reveal(id); return; }

  heard(opts.said ?? s.said);
  sim.setState('thinking');
  window.setTimeout(() => {
    reveal(id);
    speak(`${s.line} ${s.follow}`).then(() => renderHints(next.id));
  }, reduced() ? 0 : 380);
}

function reveal(id: string) {
  transition(() => show(id));
  history.replaceState(null, '', '#' + id);
  if (narrow()) window.setTimeout(() => $('#panel').scrollIntoView({ behavior: reduced() ? 'auto' : 'smooth' }), 300);
}

function closeSection(opts: { fromBrain?: boolean } = {}) {
  if (!active) return;
  if (active === 'page') pageId = null;
  if (provisioned && !live) { reset(); return; }
  transition(() => show(null));
  history.replaceState(null, '', location.pathname + location.search);
  if (live) { if (!opts.fromBrain) live.event({ event: 'section_closed', payload: {} }); renderHints(); return; }
  speak('Where to next?').then(() => renderHints());
}

/* ---------- hints and counter ---------- */
/** Things to say next. Spoken, not clicked; clickable only in the simulated fallback. */
function renderHints(nextId?: string) {
  hintsEl.textContent = '';
  const order: SectionDef[] = [...SECTIONS.filter((s) => !visited.has(s.id)), ...SECTIONS.filter((s) => visited.has(s.id))];
  const pick = nextId ? [SECTIONS.find((s) => s.id === nextId)!, ...order.filter((s) => s.id !== nextId)] : order;
  // With a section open, the first thing to say works inside it (rupees, the developer tab):
  // it shows the visitor that she can do more than open sections.
  const here = SECTIONS.find((s) => s.id === active)?.try;
  type Hint = { said: string; go: () => void };
  const hints: Hint[] = pick.filter((s) => s.id !== active).map((s) => ({ said: s.said, go: () => openSection(s.id, { said: s.said }) }));
  if (here) hints.unshift({ said: here.said, go: () => { heard(here.said); showTarget(here.target); } });
  hints.slice(0, 4).forEach((s, i) => {
    const li = document.createElement('li');
    li.style.setProperty('--h', String(i));
    // A small drawn waveform: this is something to say out loud.
    li.innerHTML = '<svg class="hint__mark" viewBox="0 0 14 12" aria-hidden="true"><rect x="0" y="4" width="2" height="4" rx="1"/><rect x="4" y="1" width="2" height="10" rx="1"/><rect x="8" y="3" width="2" height="6" rx="1"/><rect x="12" y="5" width="2" height="2" rx="1"/></svg>';
    const text = s.said.replace(/[.?]$/, '');
    if (provisioned) {
      const span = document.createElement('span');
      span.textContent = text;
      li.append(span);
    } else {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = text;
      b.addEventListener('click', s.go);
      li.append(b);
    }
    hintsEl.append(li);
  });
}

function countTo(n: number) {
  const from = Number(savedEl.textContent) || 0;
  if (reduced()) { savedEl.textContent = String(n); return; }
  const t0 = performance.now();
  const step = (now: number) => {
    const k = Math.min(1, (now - t0) / 600);
    savedEl.textContent = String(Math.round(from + (n - from) * k));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* ---------- the live call ---------- */
function applyAction(a: UiAction) {
  switch (a.command) {
    case 'open_section': openSection(a.payload.section, { fromBrain: true }); return;
    case 'show': showTarget(a.payload.target, { fromBrain: true }); return;
    case 'open_link': showLink(a.payload.link); return;
    case 'open_page': openPage(a.payload.page, { fromBrain: true }); return;
    case 'close_section': closeSection({ fromBrain: true }); return;
    case 'set_mode':
      setMode(a.payload.mode, { fromBrain: true });
      if (a.payload.mode === 'read') { endedBy = 'read_mode'; live?.endWhenQuiet(); }
      return;
    case 'site_command': track('site_command', { command: a.payload.command }); runCommand(a.payload.command); return;
    // She says goodbye first; the call ends when she finishes, and the page resets.
    case 'end_conversation': endedBy = 'tanvi'; live?.endWhenQuiet(); return;
    default: unhandledUiAction(a);
  }
}

/** Open the target's section if it is not open, then switch, press or point at the target. */
function showTarget(id: string, opts: { fromBrain?: boolean } = {}) {
  const t = TARGETS.find((x) => x.id === id);
  if (!t) return;
  track('section_control', { target: id, section: t.section ?? (t.page ? `page:${t.page}` : null), by: opts.fromBrain ? 'tanvi' : 'visitor' });
  if (t.page && t.part) { openPage(t.page, opts); whenPageReady(() => pointInPage(t.part!)); return; }
  const opened = active !== t.section;
  if (opened) openSection(t.section, { fromBrain: opts.fromBrain });
  act(id, opened);
}

/** Another page of the site, beside Tanvi in place of a section: the call carries on.
 *  In Read mode (or with nothing to show it in) it is an ordinary visit. */
function openPage(id: string, opts: { fromBrain?: boolean } = {}) {
  const p = PAGES.find((x) => x.id === id);
  if (!p) return;
  if (pageId !== id || active !== 'page') track('page_opened', { page: id, by: opts.fromBrain ? 'tanvi' : 'visitor', in_call: Boolean(live) });
  if (body.dataset.mode !== 'talk') setMode('talk', { fromBrain: opts.fromBrain });
  start();
  if (live && !opts.fromBrain) live.event({ event: 'page_opened', payload: { page: id as OpenPage['page'] } });
  const src = `${p.url}?frame=1`;
  if (pageId !== id || !pageView.getAttribute('src')) { pageReady = false; pageView.setAttribute('src', src); }
  pageId = id;
  if (active !== 'page') transition(() => show('page'));
  else { saveState(); attend(attended()); }
  history.replaceState(null, '', location.pathname + location.search);
  // On a phone the page fills the screen under the header (CSS); the page behind it goes back to the top.
  if (narrow()) window.scrollTo({ top: 0 });
  if (!live && !provisioned) speak(`${p.title}. ${p.does}`).then(() => renderHints());
  else renderHints();
}

/* Inside a page beside Tanvi, links stay beside her: another site page opens in its place, a link
   home opens that section, anything else on the site loads in the frame, and other sites get a tab. */
let pageReady = false;
const waiting: Array<() => void> = [];
/** Run once the page beside Tanvi has loaded (now, if it already has). */
function whenPageReady(fn: () => void) {
  if (pageReady) window.setTimeout(fn, 0);
  else waiting.push(fn);
}

/** Scroll the page beside Tanvi to one of its parts, and mark the part's heading. */
function pointInPage(part: string) {
  const doc = pageView.contentDocument;
  const win = pageView.contentWindow;
  const el = doc?.querySelector<HTMLElement>(`[data-part="${part}"]`);
  if (!doc || !win || !el) return;
  win.scrollTo({ top: el.getBoundingClientRect().top + win.scrollY - 24, behavior: reduced() ? 'auto' : 'smooth' });
  doc.querySelectorAll('.is-marked').forEach((h) => h.classList.remove('is-marked'));
  const heading = el.querySelector<HTMLElement>('h1, h2, h3, .demo__title') ?? el;
  heading.classList.add('is-marked');
}

pageView.addEventListener('load', () => {
  pageReady = true;
  waiting.splice(0).forEach((fn) => window.setTimeout(fn, 120));
  const doc = pageView.contentDocument;
  if (!doc) return;
  try { const t = document.documentElement.dataset.theme; if (t) doc.documentElement.dataset.theme = t; } catch { /* ignore */ }
  doc.addEventListener('click', (e) => {
    const a = (e.target as Element).closest<HTMLAnchorElement>('a[href]');
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey) return;
    const url = new URL(a.href, pageView.contentWindow!.location.href);
    if (url.origin !== location.origin) { a.target = '_blank'; a.rel = 'noopener'; return; }
    e.preventDefault();
    const page = pageAt(url.pathname);
    const section = url.pathname === '/' ? url.hash.replace(/^#s?-?/, '') : '';
    if (page) openPage(page.id);
    else if (section && SECTIONS.some((s) => s.id === section)) openSection(section);
    else if (url.pathname === '/') closeSection();
    else { url.searchParams.set('frame', '1'); pageView.setAttribute('src', url.pathname + url.search + url.hash); }
  });
});

/** A page outside this one, as a link under Tanvi. A browser blocks a tab opened with no
 *  click behind it, so she hands the visitor the link to click instead. */
function showLink(id: string) {
  const l = LINKS.find((x) => x.id === id);
  if (!l) return;
  track('link_offered', { link: id });
  linkCard.dataset.link = id;
  // The console follows the environment: Base.astro has already pointed every Console link on the
  // page at the right one, so use theirs.
  const url = l.id === 'console' ? $<HTMLAnchorElement>('a[data-console]')?.href || l.url : l.url;
  linkCard.href = url;
  $('.linkcard__label', linkCard).textContent = l.label;
  $('.linkcard__url', linkCard).textContent = url.startsWith('/') ? 'voqalize.com' + url : url.replace(/^https?:\/\//, '').replace(/\/$/, '');
  linkCard.hidden = false;
  linkCard.classList.remove('is-new');
  void linkCard.offsetWidth;
  linkCard.classList.add('is-new');
  if (!linkCard.getBoundingClientRect().height) return;
  const r = linkCard.getBoundingClientRect();
  if (r.bottom > innerHeight || r.top < 0) linkCard.scrollIntoView({ block: 'center', behavior: reduced() ? 'auto' : 'smooth' });
}

async function goLive(opts: { rejoin?: boolean } = {}) {
  if (live || connecting) return;
  connecting = true;
  callT0 = performance.now();
  callUp = false;
  endedBy = 'dropped';
  track('call_started', { rejoin: Boolean(opts.rejoin) });
  start();
  body.classList.add('is-connecting');
  note.textContent = opts.rejoin ? '' : 'Connecting. Allow the microphone when your browser asks.';
  try {
    live = await startCall({
      status: (s, message) => {
        if (s === 'live' && !callUp) {
          callUp = true;
          track('call_connected', { rejoin: Boolean(opts.rejoin), seconds_to_connect: Math.round((performance.now() - callT0) / 100) / 10 });
        }
        if (s === 'live') { body.classList.remove('is-connecting'); body.classList.add('is-live'); note.textContent = ''; }
        if (s === 'ended' || s === 'error') endLive(message);
      },
      state: setState,
      botTurn: () => { caption.classList.remove('intro'); caption.textContent = ''; },
      botText: (text) => {
        $$('.w.now', caption).forEach((w) => w.classList.remove('now'));
        text.split(/\s+/).filter(Boolean).forEach((w, i, all) => { const s = appendWord(w, true); if (i === all.length - 1) s.classList.add('now'); });
        ribbon.pulse();
      },
      heard: (text) => heard(text),
      action: applyAction,
    }, opts);
    if (readMuted()) setMuted(true);
    renderHints(active ? undefined : SECTIONS[0].id);
    // What is on their screen, each time it settles: Tanvi talks about what they actually see.
    stopViewing = watchViewing(viewSource, (v) => live?.event({ event: 'viewing', payload: v }));
  } catch {
    /* endLive already ran with the reason */
  } finally {
    connecting = false;
  }
}

function endLive(message?: string) {
  const seconds = Math.round((performance.now() - callT0) / 1000);
  if (message) {
    track('call_failed', { message, seconds });
    trackError(new Error(`Live call failed to start: ${message}`), { stage: 'connect' });
  } else {
    track('call_ended', { seconds, ended_by: endedBy, sections_opened: visited.size });
  }
  live = null;
  stopViewing?.();
  stopViewing = null;
  setMuted(false);
  forgetState();
  body.classList.remove('is-live', 'is-connecting');
  face.classList.remove('has-live-face');
  setState('idle');
  reset();
  note.textContent = message ? `Could not start the call: ${message}` : '';
}

/** Back to the first screen: Tanvi centre stage, the headline, the four verbs and the two buttons. */
function reset() {
  if (active) transition(() => show(null));
  history.replaceState(null, '', location.pathname + location.search);
  started = false;
  body.classList.remove('is-started');
  visited.clear();
  saved = 0;
  savedEl.textContent = '0';
  caption.classList.add('intro');
  caption.innerHTML = introHTML;
  heard('');
  hintsEl.textContent = '';
  linkCard.hidden = true;
}

// The visitor's own presses on a tab, a step or a switch: Tanvi hears about them.
onVisitorControl((target) => {
  track('section_control', { target, section: TARGETS.find((t) => t.id === target)?.section ?? null, by: 'visitor' });
  live?.event({ event: 'control_used', payload: { target: target as Show['target'] } });
});

// The link card under Tanvi: a console link here is a conversion like any other.
linkCard.addEventListener('click', () => {
  const link = linkCard.dataset.link ?? '';
  track('link_clicked', { link }, true);
  if (link === 'console') track('console_clicked', { placement: 'tanvi_link', section: active, plan: null, label: 'Tanvi link card' }, true);
});

// In Talk mode the header's Experience Center opens beside Tanvi, so the call carries on.
$$<HTMLAnchorElement>('a.top__cta').forEach((a) => a.addEventListener('click', (e) => {
  if (body.dataset.mode !== 'talk' || e.metaKey || e.ctrlKey || e.shiftKey) return;
  e.preventDefault();
  openPage('experience');
}));

$$('[data-hang]').forEach((b) => b.addEventListener('click', () => { endedBy = 'visitor'; live?.hangUp(); }));

/* Mute: the visitor's microphone only. Remembered for this tab, so a refresh keeps it. */
let muted = false;
function readMuted(): boolean { try { return sessionStorage.getItem('vq-muted') === '1'; } catch { return false; } }
function setMuted(on: boolean) {
  muted = on;
  live?.mute(on);
  muteBtn.setAttribute('aria-pressed', String(on));
  muteBtn.setAttribute('aria-label', on ? 'Unmute your microphone' : 'Mute your microphone');
  $('.lbl', muteBtn).textContent = on ? 'Unmute' : 'Mute';
  try { if (on) sessionStorage.setItem('vq-muted', '1'); else sessionStorage.removeItem('vq-muted'); } catch { /* ignore */ }
}
muteBtn.addEventListener('click', () => { setMuted(!muted); track('mic_muted', { on: muted }); });

/* What a refresh should bring back during a call: the open section and the tally. Per tab. */
const STATE_KEY = 'vq-talk';
function saveState() {
  if (!live) return;
  try { sessionStorage.setItem(STATE_KEY, JSON.stringify({ active, page: pageId, visited: [...visited], saved })); } catch { /* ignore */ }
}
function forgetState() { try { sessionStorage.removeItem(STATE_KEY); } catch { /* ignore */ } }
function restoreState() {
  try {
    const s = JSON.parse(sessionStorage.getItem(STATE_KEY) || 'null') as { active: string | null; page?: string | null; visited: string[]; saved: number } | null;
    if (!s) return;
    s.visited.forEach((v) => visited.add(v));
    saved = s.saved;
    savedEl.textContent = String(saved);
    if (s.active === 'page' && s.page) { const p = PAGES.find((x) => x.id === s.page); if (p) { pageId = p.id; pageView.setAttribute('src', `${p.url}?frame=1`); show('page'); } }
    else if (s.active) show(s.active);
  } catch { /* ignore */ }
}

/* ---------- start ---------- */
function start() {
  if (started) return;
  started = true;
  body.classList.add('is-started');
}
function greet() {
  track('talk_clicked', { voice: provisioned ? 'live' : 'simulated' });
  if (provisioned) { void goLive(); return; }
  const first = !started;
  start();
  heard('');
  if (first) speak("Hi, I'm Tanvi. I'll show you Voqalize just by talking, and I'll do the clicking. What are you building?").then(() => renderHints(SECTIONS[0].id));
}

$$('[data-talk]').forEach((b) => b.addEventListener('click', () => { setMode('talk'); greet(); }));
$$('[data-set-mode]').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.setMode as Mode)));
$$<HTMLAnchorElement>('[data-goto]').forEach((a) => a.addEventListener('click', (e) => {
  if (body.dataset.mode !== 'talk') return;
  e.preventDefault();
  const s = SECTIONS.find((x) => x.id === a.dataset.goto);
  openSection(a.dataset.goto!, { said: s?.said });
}));
$$('[data-ask-about]').forEach((b) => b.addEventListener('click', () => {
  const s = SECTIONS.find((x) => x.id === b.dataset.askAbout);
  openSection(b.dataset.askAbout!, { said: s?.said });
}));
// Escape is the quiet way out of a section; in a conversation, saying "go back" does it.
addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && active) closeSection();
});

/* ---------- the phone view's copy of the page ---------- */
// "Show me this on a phone" frames a copy of the site; that copy is a plain Read-mode
// page with no call and no face of its own.
const embedded = new URLSearchParams(location.search).get('embed') === '1';
if (embedded) body.classList.add('is-embed');

/* ---------- Tanvi's face, idle, before any call ---------- */
if (provisioned && !embedded) {
  body.classList.add('is-provisioned');
  prepare($('#face-live'), () => face.classList.add('has-live-face'));
  // A refresh during a conversation: rejoin it, no button, same session.
  if (hasLiveCall()) {
    setMode('talk', { scroll: false, fromBrain: true });
    start();
    caption.classList.remove('intro');
    caption.textContent = '';
    restoreState();
    void goLive({ rejoin: true });
  }
}

/* ---------- typed fallback (simulated voice only) ---------- */
// With no live voice there is no way to speak, so a typed request still routes.
// It is not shown anywhere; it exists for development and for the keyboard.
function routeTyped(text: string) {
  const cmd = commandFor(text);
  if (cmd) { runCommand(cmd); return; }
  const hit = routeSection(text);
  if (hit) openSection(hit.id, { said: text });
}

/* ---------- phones: Tanvi as a tile you can move ---------- */
// With a section open on a phone, Tanvi shrinks to a tile in a corner, with End and
// Mute under her. Drag her anywhere; she settles in the nearest corner and stays there.
function mountTile() {
  const guide = $('.guide');
  const CORNER = 'vq-corner';
  let corner = 'br';
  try { corner = sessionStorage.getItem(CORNER) || 'br'; } catch { /* ignore */ }
  guide.dataset.corner = corner;
  let start: { x: number; y: number; dx: number; dy: number } | null = null;
  const tiled = () => narrow() && app.classList.contains('is-split') && body.dataset.mode === 'talk';
  face.addEventListener('pointerdown', (e) => {
    if (!tiled()) return;
    const r = guide.getBoundingClientRect();
    start = { x: e.clientX, y: e.clientY, dx: e.clientX - r.left, dy: e.clientY - r.top };
    face.setPointerCapture(e.pointerId);
    guide.classList.add('is-dragging');
  });
  face.addEventListener('pointermove', (e) => {
    if (!start) return;
    guide.style.left = `${e.clientX - start.dx}px`;
    guide.style.top = `${e.clientY - start.dy}px`;
  });
  const drop = (e: PointerEvent) => {
    if (!start) return;
    start = null;
    guide.classList.remove('is-dragging');
    guide.style.left = guide.style.top = '';
    corner = (e.clientY < innerHeight / 2 ? 't' : 'b') + (e.clientX < innerWidth / 2 ? 'l' : 'r');
    guide.dataset.corner = corner;
    try { sessionStorage.setItem(CORNER, corner); } catch { /* ignore */ }
  };
  face.addEventListener('pointerup', drop);
  face.addEventListener('pointercancel', drop);
}

/* ---------- first paint ---------- */
const params = new URLSearchParams(location.search);
let initial: Mode = 'talk';
try { if (localStorage.getItem('vq-mode') === 'read') initial = 'read'; } catch { /* ignore */ }
const asked = params.get('mode');
if (asked === 'read' || asked === 'talk') initial = asked;
if (embedded) initial = 'read';
setMode(initial, { scroll: false });
mountMotion();
mountTile();
const hashId = location.hash.slice(1);
if (hashId && SECTIONS.some((s) => s.id === hashId)) {
  if (initial === 'talk') openSection(hashId);
  else document.getElementById('s-' + hashId)?.scrollIntoView();
}
body.classList.add('is-ready');

/* Hooks for debugging and for anything else on the page that wants to drive the shell. */
declare global {
  interface Window { vq: { open: (id: string) => void; close: () => void; mode: (m: Mode) => void; say: (text: string) => void; act: (a: UiAction) => void; view: () => Viewing } }
}
// `act` applies a brain action exactly as a live call would; the end-to-end tests drive the page with it.
window.vq = { open: (id) => openSection(id), close: () => closeSection(), mode: (m) => setMode(m), say: routeTyped, act: applyAction, view: () => snapshot(viewSource) };
