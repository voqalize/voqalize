/**
 * The avatars on the strip, and how a page mounts one.
 *
 * Every one comes from `@voqalize/avatar`, installed from npm — including tara, who
 * used to be vendored here as a proprietary build. Since 0.4.0 the 2.5-D
 * characters ship in the package like every other face: MIT code, and their
 * character binaries under CC-BY 4.0. Nothing in this repository is anyone's
 * source any more, and there is no second copy of a face to keep in step.
 *
 * `@voqalize/avatar` ships faces in different shapes, and this file's job is to
 * make them one shape. A line-art face is a *drawing* handed to the bundled SVG avatar; a
 * canvas avatar and a 2.5-D character are each a whole `createAvatar` module of
 * their own. The published interface is the module
 * (`createAvatar({mount, client}) -> {destroy()}`), so the drawings are wrapped
 * into that same interface here and the page never branches again.
 *
 * A face on the strip needs a name, a blurb and a paired voice in
 * `backend/content.py`, which is an editorial choice and not an import.
 *
 * Every entry is loaded on demand. The painted faces carry wardrobe images and
 * the 2.5-D ones a character binary, and a page that imported every face up
 * front would put megabytes in front of the greeting for faces nobody is
 * looking at.
 *
 * **The name, the blurb and the voice are the brain's** (`backend/content.py`).
 * What is duplicated here is only what the page cannot be told in time: the key
 * of the avatar the call opens on, which has to be on screen before the brain
 * has been dialled. If you add an avatar, add it in both places — the sweep in
 * `demos/tests/test_demo_voice_contract.py` will not catch a face that is on the
 * strip and unknown to the brain.
 */

import { createAvatar as createSvgAvatar } from "@voqalize/avatar";
import type { AvatarFactory, AvatarOptions, Face } from "@voqalize/avatar";

/** The face the strip starts on, and so the one a call opens on unless the
 *  visitor picks another. Must equal `DEFAULT_AVATAR` in `backend/content.py`. */
export const DEFAULT_AVATAR = "tanya";

export interface RosterEntry {
  /** The key the brain uses, and the one sent back when a visitor clicks. */
  key: string;
  /** Shown on the chip. */
  name: string;
  /** "2.5-D", "line art" or "painted" — the one thing worth saying on a chip
   *  that small. */
  kind: string;
  /** Load this avatar's implementation. Resolved once and cached by the bundler. */
  load: () => Promise<AvatarFactory<AvatarOptions>>;
}

/** Wrap a drawing as an avatar module, which is the interface everything else
 *  here speaks. `face` is read at mount, so the closure is the whole binding. */
function fromFace(
  load: () => Promise<{ default?: unknown } & Record<string, unknown>>,
  name: string,
) {
  return async (): Promise<AvatarFactory<AvatarOptions>> => {
    const mod = await load();
    const face = mod[name] as Face;
    return (options: AvatarOptions) => createSvgAvatar({ ...options, face });
  };
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
    key: "myna",
    name: "Myna",
    kind: "line art",
    load: fromFace(() => import("@voqalize/avatar/faces/myna"), "myna"),
  },
  {
    key: "peep",
    name: "Peep",
    kind: "line art",
    load: fromFace(() => import("@voqalize/avatar/faces/peep"), "peep"),
  },
  {
    key: "wren",
    name: "Wren",
    kind: "line art",
    load: fromFace(() => import("@voqalize/avatar/faces/wren"), "wren"),
  },
  {
    key: "arjun",
    name: "Arjun",
    kind: "painted",
    load: () => import("@voqalize/avatar/avatars/arjun").then((m) => m.createAvatar),
  },
  {
    key: "meera",
    name: "Meera",
    kind: "painted",
    load: () => import("@voqalize/avatar/avatars/meera").then((m) => m.createAvatar),
  },
  {
    key: "vikram",
    name: "Vikram",
    kind: "painted",
    load: () => import("@voqalize/avatar/avatars/vikram").then((m) => m.createAvatar),
  },
  {
    key: "ishita",
    name: "Ishita",
    kind: "painted",
    load: () => import("@voqalize/avatar/avatars/ishita").then((m) => m.createAvatar),
  },
  {
    key: "kabir",
    name: "Kabir",
    kind: "painted",
    load: () => import("@voqalize/avatar/avatars/kabir").then((m) => m.createAvatar),
  },
  {
    key: "naina",
    name: "Naina",
    kind: "painted",
    load: () => import("@voqalize/avatar/avatars/naina").then((m) => m.createAvatar),
  },
];

export const ROSTER_BY_KEY: Record<string, RosterEntry> = Object.fromEntries(
  ROSTER.map((entry) => [entry.key, entry]),
);
