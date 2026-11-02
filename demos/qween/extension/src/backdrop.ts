/**
 * What stands behind Trisha: a softly out-of-focus Qween salon in their teal,
 * a lit arch behind her head and brass shelves at the edges. The avatar draws
 * her on a transparent canvas, so this layer is all that shows around her.
 *
 * It is mostly still, as a real room behind a person is. Now and then, while
 * she is not speaking, the lamp over the arch slowly warms the room a little, or
 * one or two of the shelves' points of light glint. That is the whole of it:
 * the card is small, so anything that moves sits right beside her face and
 * pulls the eye off her lips. So a change is rare (every 20–40 s), slow to
 * come and go (a sudden change catches the eye; a slow one is felt more than
 * seen), and small. Nothing moves while she speaks, in the
 * minimised bubble, in a hidden tab, or for a visitor who asks for less
 * motion. No video: one still and a few gradients, animated by the
 * compositor, which costs a phone nothing beside the avatar.
 *
 * The image is generated (gpt-image-2, 2026-11-02), not Qween's photography:
 * their site has no interior that works behind a portrait. The prompt:
 * "A jewellery salon wall painted deep muted teal-green (close to #0e4a48),
 * with a large softly lit arched niche behind the centre giving a gentle warm
 * glow, a few out-of-focus brass picture lights and small warm golden bokeh
 * points toward the edges", as a background plate with no person, text, logo
 * or jewellery in focus, shot at 85mm f/1.4. Shipped at 512 px, WebP q90,
 * inlined into the bundle.
 */
import salon from "./assets/salon.webp";

/** The points of light on the shelves, as percentages of the plate, read off
 *  the image's warm local maxima that her hair and shoulders leave visible.
 *  A new plate needs these read again. */
const GLINTS: readonly [left: number, top: number][] = [
  [2.5, 43.5],
  [10, 45],
  [94, 41.5],
  [97.5, 46],
  [1.5, 64],
];

/** The wait between changes, in ms: the owner's 20–40 s. */
const EVERY = [20_000, 40_000] as const;
/** The first one comes sooner, so a short call sees the room is alive. */
const FIRST = [10_000, 18_000] as const;
/** A change that comes due while one may not run waits this long and asks again. */
const RETRY = 4_000;
/** The lamp's rise and fall. The arch itself is behind her head, so the light
 *  is a wash over the upper wall and the shelves either side of her: lit only
 *  inside the arch, what her silhouette leaves visible brightened 0.7%, which
 *  nobody sees. At this peak the visible wall rises from a mean of 30 to about
 *  37 of 255 (measured through her matte on the rendered card, 2026-11-02). */
const BREATH_MS = 7_000;
const BREATH_PEAK = 0.12;
const GLINT_MS = 2_600;
const GLINT_PEAK = 0.7;
/** How fast a change gives way when she starts to speak. */
const YIELD_MS = 800;

export const BACKDROP_STYLES = `
.backdrop {
  position: absolute; inset: 0; overflow: hidden; isolation: isolate;
  background: #0b3433 url("${salon}") center / cover no-repeat;
}
.backdrop i { position: absolute; display: block; mix-blend-mode: screen; pointer-events: none; opacity: 0; }
.backdrop .lamp {
  left: -25%; top: -35%; width: 150%; height: 110%;
  background: radial-gradient(closest-side, rgba(255, 206, 140, 0.9), rgba(255, 190, 120, 0.4) 60%, transparent);
}
.backdrop .glint {
  width: 9%; height: 9%; transform: translate(-50%, -50%);
  background: radial-gradient(closest-side, rgba(255, 232, 196, 1), rgba(255, 196, 120, 0.6) 40%, transparent);
}
`;

export const BACKDROP_HTML = `<div class="backdrop" aria-hidden="true"><i class="lamp"></i>${GLINTS.map(
  ([x, y]) => `<i class="glint" style="left:${x}%;top:${y}%"></i>`,
).join("")}</div>`;

const between = ([lo, hi]: readonly [number, number]) => lo + Math.random() * (hi - lo);

/**
 * Runs the room's changes while a call is live. `root` carries the widget's
 * state: `data-activity` and `data-min`.
 */
export function animateBackdrop(root: HTMLElement, backdrop: HTMLElement) {
  const lamp = backdrop.querySelector<HTMLElement>(".lamp")!;
  const glints = [...backdrop.querySelectorAll<HTMLElement>(".glint")];
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
  let timer: ReturnType<typeof setTimeout> | undefined;
  let running: Animation[] = [];

  const mayMove = () =>
    root.dataset.activity !== undefined &&
    root.dataset.activity !== "speaking" &&
    !root.hasAttribute("data-min") &&
    document.visibilityState === "visible" &&
    !calm.matches;

  function breathe(): Animation[] {
    return [
      lamp.animate([{ opacity: 0 }, { opacity: BREATH_PEAK, offset: 0.45 }, { opacity: 0 }], {
        duration: BREATH_MS,
        easing: "ease-in-out",
      }),
    ];
  }

  function glint(): Animation[] {
    const picked = [...glints].sort(() => Math.random() - 0.5).slice(0, Math.random() < 0.5 ? 1 : 2);
    return picked.map((g, i) =>
      g.animate(
        [
          { opacity: 0, transform: "translate(-50%, -50%) scale(0.6)" },
          { opacity: GLINT_PEAK, transform: "translate(-50%, -50%) scale(1)", offset: 0.4 },
          { opacity: 0, transform: "translate(-50%, -50%) scale(0.85)" },
        ],
        { duration: GLINT_MS, delay: i * 700, easing: "ease-in-out" },
      ),
    );
  }

  function schedule(wait: number): void {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (!mayMove() || running.length) return schedule(RETRY);
      running = Math.random() < 0.6 ? breathe() : glint();
      const done = running;
      void Promise.all(done.map((a) => a.finished.catch(() => undefined))).then(() => {
        if (running === done) running = [];
      });
      schedule(between(EVERY));
    }, wait);
  }

  /** She began to speak, or the card went away: what is lit fades out quickly
   *  from wherever it is, rather than snapping off. */
  function yieldNow(): void {
    for (const a of running) {
      const el = (a.effect as KeyframeEffect | null)?.target as HTMLElement | null;
      if (!el || a.playState !== "running") continue;
      const now = getComputedStyle(el);
      const from = { opacity: now.opacity, transform: now.transform };
      a.cancel();
      el.animate([from, { opacity: 0, transform: from.transform }], { duration: YIELD_MS, easing: "ease-out" });
    }
    running = [];
  }

  new MutationObserver(() => {
    if (!mayMove()) yieldNow();
  }).observe(root, { attributes: true, attributeFilter: ["data-activity", "data-min"] });

  return {
    start: () => schedule(between(FIRST)),
    stop: () => {
      clearTimeout(timer);
      yieldNow();
    },
  };
}
