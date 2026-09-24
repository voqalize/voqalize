/**
 * The avatars on the strip, and how a page mounts one.
 *
 * Every one comes from `@voqalize/avatar`, installed from npm — including tara, who
 * used to be vendored here as a proprietary build. Since 0.4.0 the 2.5-D
 * characters ship in the package like every other face: MIT code, and their
 * character binaries under CC-BY 4.0. Nothing in this repository is anyone's
 * source any more, and there is no second copy of a face to keep in step.
 *
 * The strip carries the 2.5-D characters and nothing else. The package also
 * ships line-art faces, and they are still the library's; this page
 * stopped showing them on 2026-09-21 because a visitor judges the library by
 * the best face on it, and the 2.5-D ones are that. Each is a whole
 * `createAvatar` module, so there is nothing here to adapt.
 *
 * A face on the strip needs a name, a blurb and a paired voice in
 * `backend/content.py`, which is an editorial choice and not an import.
 *
 * Every entry is loaded on demand. Each carries a character binary, and a
 * page that imported every face up front would put megabytes in front of the
 * greeting for faces nobody is looking at.
 *
 * **The name, the blurb and the voice are the brain's** (`backend/content.py`).
 * What is duplicated here is only what the page cannot be told in time: the key
 * of the avatar the call opens on, which has to be on screen before the brain
 * has been dialled. If you add an avatar, add it in both places — the sweep in
 * `demos/tests/test_demo_voice_contract.py` will not catch a face that is on the
 * strip and unknown to the brain.
 */

import type { AvatarFactory, AvatarOptions } from "@voqalize/avatar";

/** The face the strip starts on, and so the one a call opens on unless the
 *  visitor picks another. Must equal `DEFAULT_AVATAR` in `backend/content.py`. */
export const DEFAULT_AVATAR = "tanya";

export interface RosterEntry {
  /** The key the brain uses, and the one sent back when a visitor clicks. */
  key: string;
  /** Shown on the chip. */
  name: string;
  /** What kind of face it is — the one thing worth saying on a chip that
   *  small. */
  kind: string;
  /** Load this avatar's implementation. Resolved once and cached by the bundler. */
  load: () => Promise<AvatarFactory<AvatarOptions>>;
}

export const ROSTER: readonly RosterEntry[] = [
  {
    key: "tanya",
    name: "Tanya",
    kind: "2.5-D",
    load: () => import("@voqalize/avatar/avatars/tanya").then((m) => m.createAvatar),
  },
  {
    key: "tess",
    name: "Tess",
    kind: "2.5-D",
    load: () => import("@voqalize/avatar/avatars/tess").then((m) => m.createAvatar),
  },
  {
    key: "tushar",
    name: "Tushar",
    kind: "2.5-D",
    load: () => import("@voqalize/avatar/avatars/tushar").then((m) => m.createAvatar),
  },
  {
    key: "tara",
    name: "Tara",
    kind: "2.5-D",
    load: () => import("@voqalize/avatar/avatars/tara").then((m) => m.createAvatar),
  },
  {
    key: "tanvi",
    name: "Tanvi",
    kind: "2.5-D",
    load: () => import("@voqalize/avatar/avatars/tanvi").then((m) => m.createAvatar),
  },
];

export const ROSTER_BY_KEY: Record<string, RosterEntry> = Object.fromEntries(
  ROSTER.map((entry) => [entry.key, entry]),
);
