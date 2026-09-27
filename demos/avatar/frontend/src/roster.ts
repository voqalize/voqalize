/**
 * The characters on the strip.
 *
 * A character is a name. `@voqalize/avatar` takes it as `character` and fetches
 * the avatar runtime and that character from `avatar.voqalize.com` when the face
 * mounts, so nothing here is imported and a face nobody picks is never
 * downloaded. The key is the character's name in the package.
 *
 * **The name, the blurb and the voice are the brain's** (`backend/content.py`).
 * What is duplicated here is only what the page cannot be told in time: the key
 * of the avatar the call opens on, which has to be on screen before the brain
 * has been dialled. If you add an avatar, add it in both places — the sweep in
 * `demos/tests/test_demo_voice_contract.py` will not catch a face that is on the
 * strip and unknown to the brain.
 */

/** The face the strip starts on, and so the one a call opens on unless the
 *  visitor picks another. Must equal `DEFAULT_AVATAR` in `backend/content.py`. */
export const DEFAULT_AVATAR = "tanya";

export interface RosterEntry {
  /** The character's name in `@voqalize/avatar`, the key the brain uses, and
   *  the one sent back when a visitor clicks. */
  key: string;
  /** Shown on the chip. */
  name: string;
  /** What kind of face it is — the one thing worth saying on a chip that
   *  small. */
  kind: string;
}

export const ROSTER: readonly RosterEntry[] = [
  { key: "tanya", name: "Tanya", kind: "2.5-D" },
  { key: "tess", name: "Tess", kind: "2.5-D" },
  { key: "tushar", name: "Tushar", kind: "2.5-D" },
  { key: "tara", name: "Tara", kind: "2.5-D" },
  { key: "tanvi", name: "Tanvi", kind: "2.5-D" },
];

export const ROSTER_BY_KEY: Record<string, RosterEntry> = Object.fromEntries(
  ROSTER.map((entry) => [entry.key, entry]),
);
