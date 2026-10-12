/**
 * The site's motion pieces, as step loops.
 *
 * A loop is any element with `data-loop="ms ms ms ..."`: one duration per step.
 * Step 0 is the starting picture; each later step adds a class `is-s<n>` that stays
 * on until the loop starts over, so CSS can say "from step 3 on" with `.is-s3 …`.
 * The element also carries `data-at` with the current step.
 *
 * Loops run only while they are on screen, so a section hidden in Talk mode costs
 * nothing. Reduced motion shows the finished picture and does not loop. The
 * hidden commands (pause, slower, faster, replay) act on every loop at once.
 *
 * Also here: tabs that advance on their own when a loop finishes (Talk mode has
 * nothing to click), and the carousel the shift story uses in Read mode.
 */
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

interface Run { el: HTMLElement; steps: number[]; at: number; timer: number; visible: boolean; jumped: number }
const runs = new Map<HTMLElement, Run>();
let speed = 1;
let paused = false;

function setStep(r: Run, n: number) {
  r.at = n;
  r.el.dataset.at = String(n);
  for (let i = 1; i < r.steps.length; i++) r.el.classList.toggle(`is-s${i}`, i <= n);
}

function tick(r: Run) {
  window.clearTimeout(r.timer);
  if (!r.visible || paused) return;
  r.timer = window.setTimeout(() => {
    if (r.at >= r.steps.length - 1) {
      r.el.dispatchEvent(new CustomEvent('loopend', { bubbles: true }));
      if (!r.el.isConnected || !r.visible) return;
      setStep(r, 0);
    } else setStep(r, r.at + 1);
    tick(r);
  }, r.steps[r.at] * speed);
}

/** Start a loop over from its first step (a tab was opened, or "play that again"). */
export function restart(el: HTMLElement) {
  const r = runs.get(el);
  if (!r) return;
  if (reduced()) { setStep(r, r.steps.length - 1); return; }
  setStep(r, 0);
  tick(r);
}

/** Jump a loop to step `n` and play on from there (a visitor clicked a step). */
export function goTo(el: HTMLElement, n: number) {
  const r = runs.get(el);
  if (!r) return;
  setStep(r, Math.max(0, Math.min(r.steps.length - 1, n)));
  r.jumped = Date.now();
  if (!reduced()) tick(r);
}

export function replay() {
  runs.forEach((r) => { if (r.visible) restart(r.el); });
}

export function setSpeed(f: number) {
  speed = f;
  document.documentElement.style.setProperty('--m', String(f));
}

export function setPaused(on: boolean) {
  paused = on;
  document.body.dataset.motion = on ? 'paused' : '';
  runs.forEach((r) => tick(r));
}

function mountLoops() {
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const r = runs.get(e.target as HTMLElement);
      if (!r) continue;
      const was = r.visible;
      r.visible = e.isIntersecting;
      // Coming on screen starts a loop over, unless a step was just chosen (Tanvi or a click
      // picked it while it was scrolling into view): then it plays on from there.
      if (r.visible && !was) { if (Date.now() - r.jumped < 4000) tick(r); else restart(r.el); }
      if (!r.visible) window.clearTimeout(r.timer);
    }
  }, { threshold: 0.2 });
  document.querySelectorAll<HTMLElement>('[data-loop]').forEach((el) => {
    const steps = (el.dataset.loop ?? '').split(/\s+/).map(Number).filter((n) => n > 0);
    if (steps.length < 2) return;
    runs.set(el, { el, steps, at: 0, timer: 0, visible: false, jumped: 0 });
    el.dataset.at = '0';
    io.observe(el);
  });
  // Any `[data-goto-step="n"]` inside a loop jumps it to step n.
  document.addEventListener('click', (e) => {
    const b = (e.target as Element).closest<HTMLElement>('[data-goto-step]');
    const loop = b?.closest<HTMLElement>('[data-loop]');
    if (b && loop) goTo(loop, Number(b.dataset.gotoStep));
  });
}

/* ---------- tabs ---------- */
// Clicking a tab pins it. Unpinned, the next tab opens when the current loop ends,
// so a visitor who only talks (or only watches) still sees every one.
function mountTabs() {
  document.querySelectorAll<HTMLElement>('[data-tabs]').forEach((box) => {
    const tabs = [...box.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
    const panels = [...box.querySelectorAll<HTMLElement>('[role="tabpanel"]')];
    let pinned = false;
    const open = (i: number) => {
      tabs.forEach((t, j) => { t.setAttribute('aria-selected', String(i === j)); t.tabIndex = i === j ? 0 : -1; });
      panels.forEach((p, j) => { p.hidden = i !== j; });
      const loop = panels[i]?.querySelector<HTMLElement>('[data-loop]');
      if (loop) restart(loop);
      tabs[i]?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    };
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => { pinned = true; open(i); });
      t.addEventListener('keydown', (e) => {
        const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
        if (!d) return;
        e.preventDefault();
        const n = (i + d + tabs.length) % tabs.length;
        pinned = true; open(n); tabs[n].focus();
      });
    });
    // Picking a step inside a panel also means "stay here".
    box.addEventListener('click', (e) => { if ((e.target as Element).closest('[data-goto-step]')) pinned = true; });
    box.addEventListener('loopend', (e) => {
      if (pinned || box.dataset.auto === 'off') return;
      const i = panels.findIndex((p) => !p.hidden);
      if (!panels[i]?.contains(e.target as Node)) return;
      e.stopPropagation();
      // Let the last frame breathe, then move on.
      window.setTimeout(() => open((i + 1) % tabs.length), 600 * speed);
    });
  });
}

// Links that name a tab (`data-open-tab="tab-pnp"`, or `?tab=tab-pnp` from another page) open it.
function mountTabLinks() {
  const open = (id: string | null | undefined) => { if (id) document.getElementById(id)?.click(); };
  document.addEventListener('click', (e) => open((e.target as Element).closest<HTMLElement>('[data-open-tab]')?.dataset.openTab));
  open(new URLSearchParams(location.search).get('tab'));
}

/* ---------- the carousel (shift story, Read mode on wide screens) ---------- */
function mountReels() {
  document.querySelectorAll<HTMLElement>('[data-reel]').forEach((reel) => {
    const track = reel.querySelector<HTMLElement>('.reel__track')!;
    const scenes = [...track.children] as HTMLElement[];
    const dots = [...reel.querySelectorAll<HTMLButtonElement>('.reel__dots button')];
    const go = (i: number) => {
      const n = Math.max(0, Math.min(scenes.length - 1, i));
      track.scrollTo({ left: scenes[n].offsetLeft - track.offsetLeft, behavior: reduced() ? 'auto' : 'smooth' });
    };
    const current = () => Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
    reel.querySelector('[data-reel-prev]')?.addEventListener('click', () => go(current() - 1));
    reel.querySelector('[data-reel-next]')?.addEventListener('click', () => go(current() + 1));
    dots.forEach((d, i) => d.addEventListener('click', () => go(i)));
    const sync = () => {
      const c = current();
      dots.forEach((d, i) => d.setAttribute('aria-current', String(i === c)));
      reel.dataset.first = String(c === 0);
      reel.dataset.last = String(c === scenes.length - 1);
    };
    track.addEventListener('scroll', () => requestAnimationFrame(sync), { passive: true });
    sync();
    // When a scene's motion finishes, move to the next one (the last returns to the first).
    // If the visitor takes over (arrows, dots, a swipe), hold off for a while, then carry on.
    let heldUntil = 0;
    const hold = () => { heldUntil = Date.now() + 12000; };
    const held = () => Date.now() < heldUntil;
    reel.querySelectorAll('.reel__nav button').forEach((b) => b.addEventListener('click', hold));
    // Only a real sideways swipe counts as taking over: a click or a vertical scroll does not.
    let downX = 0;
    track.addEventListener('pointerdown', (e) => { downX = e.clientX; }, { passive: true });
    track.addEventListener('pointerup', (e) => { if (Math.abs(e.clientX - downX) > 40) hold(); }, { passive: true });
    track.addEventListener('wheel', (e) => { if (Math.abs(e.deltaX) > 20 && Math.abs(e.deltaX) > 2 * Math.abs(e.deltaY)) hold(); }, { passive: true });
    reel.addEventListener('loopend', (e) => {
      const carousel = track.scrollWidth > track.clientWidth + 10;
      const c = current();
      if (held() || !carousel || !scenes[c]?.contains(e.target as Node)) return;
      window.setTimeout(() => { if (!held() && current() === c) go(c === scenes.length - 1 ? 0 : c + 1); }, 700 * speed);
    });
  });
}

/* ---------- the character wall: only what is on screen plays ---------- */
function mountVideos() {
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const v = e.target as HTMLVideoElement;
      if (e.isIntersecting && !paused && !reduced()) void v.play().catch(() => {});
      else v.pause();
    }
  }, { threshold: 0.05 });
  document.querySelectorAll<HTMLVideoElement>('video[data-autoplay]').forEach((v) => io.observe(v));
}

export function mountMotion() {
  mountLoops();
  mountTabs();
  mountTabLinks();
  mountReels();
  mountVideos();
}
