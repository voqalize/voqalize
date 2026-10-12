/**
 * The drawn products of the example store (Larkfield), shared by the hero and the
 * three story scenes. Each is the inside of a 64x48 SVG. Product colors are
 * illustration, not UI: warm, muted, never blue or purple.
 */
export const ART = {
  // Lumbar pillow: a soft rounded bolster with a strap.
  pillow: `<rect x="11" y="14" width="42" height="22" rx="11" fill="#E8DCCB" stroke="#B9A88E" stroke-width="1.2"/><path d="M18 25c6-4 22-4 28 0" fill="none" stroke="#C9B89D" stroke-width="1.2" stroke-linecap="round"/><path d="M26 14v-4h12v4" fill="none" stroke="#8E7F68" stroke-width="1.6" stroke-linecap="round"/>`,
  // Heated back wrap: a long belt with stitching and a cord to a small controller.
  wrap: `<rect x="5" y="15" width="44" height="15" rx="7.5" fill="#C9694A" stroke="#9E4F36" stroke-width="1"/><path d="M10 22.5h34" stroke="#E7A78C" stroke-width="1" stroke-dasharray="2.4 2"/><rect x="21" y="17" width="10" height="11" rx="2.5" fill="#E7A78C"/><path d="M49 22c6 0 6 10 0 13" fill="none" stroke="#6B5A4A" stroke-width="1.4" stroke-linecap="round"/><rect x="44" y="34" width="9" height="7" rx="2" fill="#4A3F36"/><circle cx="48.5" cy="37.5" r="1.3" fill="#FD5446"/>`,
  // Massage seat cushion: a seat back and base with massage nodes and a car plug.
  cushion: `<path d="M17 6h22a4 4 0 0 1 4 4v20H13V10a4 4 0 0 1 4-4z" fill="#5E5A55" stroke="#3F3B37" stroke-width="1"/><rect x="11" y="30" width="34" height="9" rx="4" fill="#4A4642" stroke="#3F3B37" stroke-width="1"/><g fill="#A9A39B"><circle cx="22" cy="13" r="2"/><circle cx="34" cy="13" r="2"/><circle cx="22" cy="20" r="2"/><circle cx="34" cy="20" r="2"/></g><path d="M45 34c6 0 9 2 9 6" fill="none" stroke="#6B5A4A" stroke-width="1.4" stroke-linecap="round"/><rect x="51" y="39" width="6" height="7" rx="1.5" fill="#3F3B37"/><rect x="53" y="44.5" width="2" height="2.5" fill="#B9A88E"/>`,
} as const;

export type ArtKey = keyof typeof ART;
