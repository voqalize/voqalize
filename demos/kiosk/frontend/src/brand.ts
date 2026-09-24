/**
 * Vantage Bank's palette and type scale — the whole of the demo's visual
 * vocabulary, in one place, because a kiosk is read standing up from a metre
 * away and every size here is a legibility decision rather than a taste one.
 *
 * Vantage Bank is invented, and so is every mark on the glass. The palette is
 * the familiar one of an Indian retail bank — a deep maroon brand and a warm
 * saffron-orange accent — because a customer walking up to a branch totem should
 * feel they are somewhere they know. Only the colours are borrowed: no real
 * bank's name, logo, wordmark or artwork appears anywhere in this demo.
 *
 * The orange is spent only on "this is the one" — a picked answer, the
 * recommended card, a live microphone. Buttons are maroon.
 *
 * There is no dark mode. A totem in a branch cubicle is lit by the branch.
 */

export const COLOR = {
  /** The brand, and every primary action. */
  brand: '#8E1E2A',
  /** Tanvi's backdrop and the room behind the totem. */
  brandDeep: '#4E0F17',
  /**
   * The one accent. Selection, the recommendation, the listening bars — never a
   * button fill, and never text on the light glass (it is under 3:1 there).
   */
  accent: '#F37321',
  /** Body text. */
  ink: '#1E1416',
  /** The glass behind everything. */
  paper: '#F4F0EE',
  /** The tray and anything lifted off the glass. */
  surface: '#FCFAF9',
  /** Eligible and confirmed states ONLY — never decoration. */
  leaf: '#1F7A5C',
  /** Hairlines and inactive rules, derived from ink. */
  rule: 'rgba(30, 20, 22, 0.12)',
  /** Secondary text. About 5.6:1 on the tray, so it still reads standing up. */
  muted: 'rgba(30, 20, 22, 0.66)',
} as const;

/**
 * The focus ring, which is an accessibility decision and not a brand one:
 * maroon on the light glass (about 9:1), the accent on the maroon backdrop,
 * where maroon would disappear.
 */
export const FOCUS = {
  ring: COLOR.brand,
  onDark: COLOR.accent,
} as const;

/**
 * Both faces load in `index.html`. Devanagari is named first in the Hindi stack
 * so a shared glyph renders in the face the rest of the line is set in.
 */
export const FONT = {
  en: '"Geist", system-ui, -apple-system, "Segoe UI", sans-serif',
  hi: '"Noto Sans Devanagari", "Geist", system-ui, sans-serif',
} as const;

/**
 * The sizes a kiosk is specified in, not the ones a laptop layout drifts to.
 * `touch` is the floor for anything a finger lands on. One radius scale:
 * `radius` for everything lifted, `pill` for the small status marks.
 */
export const SIZE = {
  touch: 60,
  body: 18,
  headline: 24,
  radius: 18,
  pill: 999,
} as const;

/**
 * The card faces. Artwork, not product copy: the terms on every card still come
 * off the wire, and a card this build does not know gets the neutral face.
 */
export const CARD_FACE: Record<string, readonly [string, string]> = {
  vantage_rise: ['#8E1E2A', '#C2413F'],
  vantage_everyday: ['#2E3A42', '#5B6972'],
  vantage_fuel: ['#7A3413', '#C4652B'],
  vantage_voyage: ['#15324F', '#2F6C9C'],
  vantage_crest: ['#17181B', '#44454C'],
};
export const CARD_FACE_FALLBACK: readonly [string, string] = ['#6E1822', '#A8323E'];

/**
 * The machine around the screen. A branch totem is a powder-coated column with
 * the panel recessed behind a bezel — hardware lives above and below the glass,
 * which is why the frame is deeper at top and bottom than at the sides.
 *
 * The glass is a tall 9:16 portrait, the shape a floor-standing totem's panel
 * actually is. Every value is a CSS length.
 */
export const CHASSIS = {
  /** The shell. Warm graphite, so it sits with the maroon rather than against it. */
  shell: '#2A2224',
  shellLit: '#3B3134',
  shellDark: '#161112',
  /** Bezel depths. */
  sides: '14px',
  top: '34px',
  bottom: '62px',
  /** The plinth the column stands on. */
  base: '40px',
  /** Height over width of the glass. */
  aspect: 16 / 9,
} as const;
