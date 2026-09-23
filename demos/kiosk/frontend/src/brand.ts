/**
 * Vantage Bank's palette and type scale — the whole of the demo's visual
 * vocabulary, in one place, because a kiosk is read standing up from a metre
 * away and every size here is a legibility decision rather than a taste one.
 *
 * Vantage Bank is invented. Nothing here is taken from a real bank.
 *
 * There is no dark mode. A totem in a branch cubicle is lit by the branch.
 */

export const COLOR = {
  /** Primary and every action. */
  amber: '#E8850B',
  /** The deep ground: the brand bar, the backdrop behind the totem. */
  umber: '#5C2018',
  /** Body text. */
  ink: '#171310',
  /** The totem's own surface. */
  paper: '#FBF7F2',
  /** Eligible and confirmed states ONLY — never decoration. */
  leaf: '#1F7A5C',
  /** Hairlines and inactive rules, derived from ink. */
  rule: 'rgba(23, 19, 16, 0.12)',
  /** Secondary text. */
  muted: 'rgba(23, 19, 16, 0.58)',
} as const;

/**
 * The focus ring, which is an accessibility decision and not a brand one.
 *
 * Amber on this paper is about 2.5:1 — under the 3:1 floor a focus indicator has
 * to clear, and a customer driving the totem from a keyboard cannot use a ring
 * they cannot find. Umber on paper is about 11:1, so that is the ring on every
 * light surface; amber is kept for the umber brand bar, where it is about 4.6:1
 * and umber would disappear.
 */
export const FOCUS = {
  /** On paper, on white, on any of the tinted panels. */
  ring: COLOR.umber,
  /** On the umber brand bar. */
  onDark: COLOR.amber,
} as const;

/**
 * Both faces load in `index.html`. Devanagari is named first in the Hindi stack
 * so a shared glyph renders in the face the rest of the line is set in.
 */
export const FONT = {
  en: '"Archivo", system-ui, -apple-system, "Segoe UI", sans-serif',
  hi: '"Noto Sans Devanagari", "Archivo", system-ui, sans-serif',
} as const;

/**
 * The sizes a kiosk is specified in, not the ones a laptop layout drifts to.
 * `touch` is the floor for anything a finger lands on.
 */
export const SIZE = {
  touch: 64,
  body: 20,
  headline: 28,
  /** Rohan's dock, bottom-right. He assists; he is not the application. */
  dock: 190,
} as const;

/**
 * The machine around the screen. A branch totem is a powder-coated column with
 * the panel recessed behind a bezel — hardware lives above and below the glass,
 * which is why the frame is deeper at top and bottom than at the sides.
 *
 * Every value is a CSS length, applied as custom properties on the chassis.
 */
export const CHASSIS = {
  /** The shell. Warm graphite, so it sits with umber rather than against it. */
  shell: '#2A2520',
  shellLit: '#3A332C',
  shellDark: '#171310',
  /** Bezel depths. */
  sides: '16px',
  top: '40px',
  bottom: '84px',
  /** The plinth the column stands on. */
  base: '56px',
} as const;
