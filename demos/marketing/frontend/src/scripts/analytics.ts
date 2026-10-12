/**
 * Analytics: PostHog, project "Voqalize Marketing Website". Loaded on every page by Base.astro.
 *
 * Consent decides how much is sent (src/scripts/consent.ts, /privacy section 15):
 * - No analytics consent yet, or declined: cookieless. No cookies, no storage, identity is a
 *   hash made on PostHog's servers. Only pageviews and page leaves go out, so traffic, sources
 *   and campaigns (UTMs, referrer) still count everyone.
 * - Analytics allowed: the full set. Autocapture, heatmaps (clicks, scroll depth, rage and dead
 *   clicks), web vitals, browser errors and console errors, and the named events below.
 * Switching in Cookie settings changes it on the spot: opt_in_capturing / opt_out_capturing.
 * No session replay and no surveys (decided 2026-10-12).
 *
 * Named events (`track`), the vocabulary for funnels and dashboards:
 *   mode_changed        {from, to, by}                  Talk or Read
 *   section_opened      {section, by}                   Talk mode: Tanvi or the visitor opened it
 *   section_viewed      {section}                       Read mode: scrolled into the middle of the screen
 *   section_engaged     {section, mode, seconds}        time a section held the screen
 *   section_control     {target, section, by}           a tab, step, switch or plan, pressed by Tanvi or the visitor
 *   page_opened         {page, by}                      another site page beside Tanvi
 *   talk_clicked / call_started / call_connected / call_ended / call_failed / mic_muted
 *   link_offered / link_clicked {link}                  the link card under Tanvi
 *   site_command        {command}                       theme, size, phone view, motion
 *   console_clicked     {placement, section, plan, label}   the conversion
 *   experience_clicked  {placement}                     the Experience Center
 *   demo_opened         {demo}                          a demo from the Experience Center
 * Every event carries `site_mode` (talk/read), `environment` (production/dev/local) and `in_frame`.
 */
import type { PostHog } from 'posthog-js';
import { allowed } from './consent';

const KEY = import.meta.env.PUBLIC_POSTHOG_KEY || 'phc_tfbA8DXmYipuou7hF8jsjGzTgFakuv6pZU6izY4UFbxk';
// Through t.voqalize.com, PostHog's managed reverse proxy on our own domain, so ad blockers don't drop
// events (docs/analytics.md). ui_host below stays PostHog's, for links into the app.
const HOST = import.meta.env.PUBLIC_POSTHOG_HOST || 'https://t.voqalize.com';

type Props = Record<string, unknown>;

const params = new URLSearchParams(location.search);
// The phone view's copy of the site (?embed=1) is a picture of the page, not a visit.
const off = params.get('embed') === '1';
const inFrame = params.get('frame') === '1';

function environment(): 'production' | 'dev' | 'local' {
  const h = location.hostname;
  if (h === 'voqalize.com' || h === 'www.voqalize.com') return 'production';
  if (/(^|\.)dev\.voqalize\.com$/.test(h)) return 'dev';
  return 'local';
}

/** What a visitor who has not allowed analytics may send: their visit, and nothing else. */
const COOKIELESS_EVENTS = new Set(['$pageview', '$pageleave']);

let ph: PostHog | null = null;

/** Sent with every event. Registered again after an opt-in, which resets PostHog's storage. */
const base = () => ({ environment: environment(), in_frame: inFrame, site_mode: document.body.dataset.mode ?? null });
function optIn(p: Pick<PostHog, 'opt_in_capturing' | 'register'>) {
  p.opt_in_capturing();
  p.register(base());
}
const queue: Array<(p: PostHog) => void> = [];
const run = (fn: (p: PostHog) => void) => (ph ? fn(ph) : queue.push(fn));

async function load() {
  const { default: posthog } = await import('posthog-js');
  posthog.init(KEY, {
    api_host: HOST,
    ui_host: 'https://us.posthog.com',
    defaults: '2026-08-30',
    // Cookieless until the visitor allows analytics; everyone starts opted out.
    cookieless_mode: 'on_reject',
    opt_out_capturing_by_default: true,
    person_profiles: 'identified_only',
    capture_pageview: 'history_change',
    capture_pageleave: true,
    autocapture: true,
    capture_heatmaps: true,
    capture_dead_clicks: true,
    capture_performance: { web_vitals: true, network_timing: false },
    capture_exceptions: { capture_unhandled_errors: true, capture_unhandled_rejections: true, capture_console_errors: true },
    disable_session_recording: true,
    disable_surveys: true,
    before_send: (e) => (e && !allowed('analytics') && !COOKIELESS_EVENTS.has(e.event) ? null : e),
    loaded: (p) => {
      p.register(base());
      if (allowed('analytics') && !p.has_opted_in_capturing()) optIn(p);
      if (!allowed('analytics') && p.has_opted_in_capturing()) p.opt_out_capturing();
    },
  });
  ph = posthog;
  // ?__posthog_debug=true: PostHog logs every call, and the instance is on window for poking.
  if (params.has('__posthog_debug')) (window as unknown as { posthog: PostHog }).posthog = posthog;
  queue.splice(0).forEach((fn) => fn(posthog));
}

if (!off) {
  void load();
  // Cookie settings changed: full tracking on, or back to cookieless.
  addEventListener('vq:consent', (e) => run((p) => {
    const on = (e as CustomEvent<{ analytics: boolean }>).detail.analytics;
    if (on && !p.has_opted_in_capturing()) optIn(p);
    if (!on && !p.has_opted_out_capturing()) { p.opt_out_capturing(); p.register(base()); }
  }));
}

/** A named event. Sent only with analytics consent; without it, nothing leaves the browser. */
export function track(event: string, props: Props = {}, beacon = false) {
  if (off || !allowed('analytics')) return;
  run((p) => p.capture(event, props, beacon ? { transport: 'sendBeacon' } : undefined));
}

/** An error the page caught itself (a call that failed to start), for error tracking. */
export function trackError(error: unknown, props: Props = {}) {
  if (off || !allowed('analytics')) return;
  const e = error instanceof Error ? error : new Error(String(error));
  run((p) => p.captureException(e, props));
}

/** Properties sent with every later event. */
export function remember(props: Props) {
  if (off) return;
  run((p) => p.register(props));
}

/* ---------- time on a section ---------- */
// One section holds the screen at a time: in Talk mode the open one, in Read mode the one
// across the middle of the viewport. The clock runs only while the tab is visible; when the
// section changes, the mode changes or the page goes away, its time is sent.
let held: { section: string; mode: string } | null = null;
let ms = 0;
let since = 0;

function pause() { if (held && since) { ms += performance.now() - since; since = 0; } }
function resume() { if (held && !since && document.visibilityState === 'visible') since = performance.now(); }

function flush(beacon = false) {
  pause();
  const seconds = Math.round(ms / 1000);
  if (held && seconds >= 1) track('section_engaged', { section: held.section, mode: held.mode, seconds }, beacon);
  ms = 0;
}

/** The section now holding the screen, or null for none. */
export function attend(section: string | null) {
  const mode = document.body.dataset.mode ?? 'read';
  if (held?.section === section && held.mode === mode) return;
  flush();
  held = section ? { section, mode } : null;
  resume();
}

addEventListener('visibilitychange', () => (document.visibilityState === 'visible' ? resume() : pause()));
addEventListener('pagehide', () => { flush(true); held = null; });

/** Read mode: the section crossing the middle of the screen holds it. */
function watchRead() {
  const viewed = new Set<string>();
  const io = new IntersectionObserver((entries) => {
    if (document.body.dataset.mode !== 'read') return;
    for (const en of entries) {
      if (!en.isIntersecting) continue;
      const id = (en.target as HTMLElement).dataset.section!;
      if (!viewed.has(id)) { viewed.add(id); track('section_viewed', { section: id }); }
      attend(id);
    }
  }, { rootMargin: '-50% 0px -50% 0px' });
  document.querySelectorAll<HTMLElement>('[data-section]:not([data-section="page"])').forEach((s) => io.observe(s));
}

/* ---------- conversions: every page ---------- */
function placement(el: Element): string {
  if (el.closest('header')) return 'header';
  if (el.closest('footer')) return 'footer';
  if (el.closest('#linkcard')) return 'tanvi_link';
  const section = el.closest<HTMLElement>('[data-section]')?.dataset.section;
  return section ? `section:${section}` : `page:${location.pathname}`;
}

document.addEventListener('click', (e) => {
  const a = (e.target as Element).closest<HTMLAnchorElement>('a[href]');
  if (!a) return;
  const where = placement(a);
  if (a.matches('[data-console]')) {
    track('console_clicked', {
      placement: where,
      section: a.closest<HTMLElement>('[data-section]')?.dataset.section ?? null,
      plan: a.closest<HTMLElement>('.plan[data-voice]')?.dataset.voice?.replace('pricing.', '') ?? null,
      label: a.textContent?.trim().replace(/\s+/g, ' ') ?? '',
    }, true);
  } else if (a.matches('[data-book]') || a.href.startsWith('https://cal.id/')) {
    track('book_call_clicked', { placement: where }, true);
  } else if (new URL(a.href, location.href).pathname === '/experience') {
    track('experience_clicked', { placement: where }, true);
  } else if (a.matches('a.demo')) {
    track('demo_opened', { demo: new URL(a.href).pathname.split('/').filter(Boolean).pop() ?? a.href }, true);
  }
}, { capture: true });

if (!off && document.querySelector('[data-section]')) watchRead();
