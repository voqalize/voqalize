/**
 * The ten avatars, and how a page mounts one.
 *
 * Nine come from the open-source `@voqalize/avatar`. The tenth, tara, is a
 * premium 3-D avatar whose code and artwork are proprietary: she is vendored as
 * a built artifact in `vendor/tara/` under her own LICENSE, not installed from
 * npm, and nothing in this repository is her source.
 *
 * Two shapes ship in `@voqalize/avatar`, and this file's job is to make them one
 * shape. A line-art face is a *drawing* handed to the bundled SVG avatar; a
 * canvas avatar is a whole `createAvatar` module of its own. The published
 * interface is the module (`createAvatar({mount, client}) -> {destroy()}`), so
 * the three faces are wrapped into that same interface here and the page never
 * branches again.
 *
 * Every entry is loaded on demand. Six of these carry wardrobe images, and a
 * page that imported all ten up front would put megabytes in front of the
 * greeting for eight faces nobody is looking at.
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
export const DEFAULT_AVATAR = "tara";

export interface RosterEntry {
  /** The key the brain uses, and the one sent back when a visitor clicks. */
  key: string;
  /** Shown on the chip. */
  name: string;
  /** "premium", "line art" or "painted" — the one thing worth saying on a chip
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
    key: "tara",
    name: "Tara",
    kind: "premium",
    load: () => import("./vendor/tara/tara.js").then((m) => m.createAvatar),
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
