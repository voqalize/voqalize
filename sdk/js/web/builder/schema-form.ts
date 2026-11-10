/**
 * The builder's form, read from the widget configuration's JSON Schema.
 *
 * Nothing here knows the configuration's fields by heart. The schema is
 * walked into leaves (one control each), and `GROUPS` only says where a leaf
 * goes; a leaf no group names lands in "More", so a field added to the schema
 * shows up in the builder with no work here. The control a leaf gets is read
 * from its schema: an enum is a choice, a boolean a switch, a hex colour a
 * colour picker, a bounded number a slider, and so on.
 *
 * The builder keeps only what the visitor changed (a sparse configuration), so
 * the snippet carries only those fields and every default stays the widget's.
 */

// ------------------------------------------------------------------- schema

/** The parts of JSON Schema the widget configuration uses. */
export interface SchemaNode {
  type?: string;
  enum?: readonly unknown[];
  const?: unknown;
  oneOf?: readonly SchemaNode[];
  properties?: Record<string, SchemaNode>;
  additionalProperties?: SchemaNode | boolean;
  items?: SchemaNode;
  default?: unknown;
  description?: string;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  title?: string;
}

export type ControlKind =
  | "choice" // an enum: segmented when short, a select when long
  | "switch" // a boolean
  | "colour" // a #rrggbb string
  | "slider" // a bounded number
  | "number" // an unbounded number
  | "text" // a string
  | "list" // an array of strings, written comma-separated
  | "json" // a free-form object (tokens, words), written as JSON
  | "presence" // `false | object`: on is the object, off is `false`
  | "background"; // the avatar's background: none, a colour, a gradient or a URL

export interface Leaf {
  /** The field's path, dot-separated: "theme.brand". */
  path: string;
  kind: ControlKind;
  label: string;
  description?: string;
  /** The schema's default, if it states one. */
  default?: unknown;
  options?: readonly string[];
  min?: number;
  max?: number;
  step?: number;
  /** Characters of free text the schema allows. */
  maxLength?: number;
  /** A leaf that only means something while another leaf is on. */
  dependsOn?: string;
}

/** Labels where the field's own name does not read well as words. */
const LABELS: Record<string, string> = {
  agent: "Agent id",
  key: "Publishable key",
  name: "Agent's name",
  avatar: "Show a face",
  "avatar.still": "Still image URL",
  "launcher.style": "Closed form",
  "launcher.label": "Launcher label",
  "launcher.tagline": "Launcher tagline",
  "open.style": "Open form",
  "open.size": "Open size",
  "collapsed.style": "Collapsed form",
  "collapsed.autoCollapse": "Collapse when cramped",
  "mobile.open": "Phone open form",
  "mobile.launcher": "Phone closed form",
  "mobile.breakpoint": "Phone below (px)",
  "placement.mode": "Placement",
  "placement.move": "Movement",
  "placement.offset": "Edge offset (px)",
  "placement.topClear": "Top clear (px)",
  "placement.avoid": "Keep clear of (selectors)",
  "controls.devices": "Device menu",
  "controls.minimise": "Minimise",
  "mic.level": "Mic level",
  "mic.instantStart": "Instant start",
  "mic.silenceHint": "Silence hint",
  "mic.pill": "Mic pill",
  "mic.coach": "Mic coach mark",
  "mic.alertTone": "Mic alert tone",
  "captions.mode": "Captions",
  "captions.lines": "Caption lines",
  "captions.linger": "Captions linger",
  "captions.showUser": "Show what the visitor said",
  "captions.position": "Captions position",
  "theme.brand": "Brand colour",
  "theme.background": "Background colour",
  "theme.ink": "Text colour",
  "theme.scheme": "Scheme",
  "theme.radius": "Corner radius (px)",
  "theme.font": "Font",
  "theme.tokens": "Theme tokens",
  dir: "Text direction",
};

/** Where each leaf goes in the form, in order. A leaf not named here goes to "More". */
export const GROUPS: readonly { id: string; title: string; paths: readonly string[] }[] = [
  {
    id: "agent",
    title: "Agent",
    paths: ["name", "launcher.label", "launcher.tagline", "agent", "key"],
  },
  {
    id: "avatar",
    title: "Avatar",
    paths: ["avatar", "avatar.character", "avatar.shape", "avatar.framing", "avatar.background", "avatar.still"],
  },
  {
    id: "placement",
    title: "Placement",
    paths: [
      "placement.mode",
      "placement.anchor",
      "placement.move",
      "placement.remember",
      "placement.offset",
      "placement.topClear",
      "placement.avoid",
    ],
  },
  {
    id: "forms",
    title: "Closed, open and collapsed",
    paths: ["launcher.style", "open.style", "open.size", "collapsed.style", "collapsed.autoCollapse"],
  },
  {
    id: "mobile",
    title: "Phones",
    paths: ["mobile.launcher", "mobile.open", "mobile.breakpoint"],
  },
  {
    id: "behaviour",
    title: "Behaviour",
    paths: [
      "mic.instantStart",
      "mic.level",
      "mic.silenceHint",
      "mic.pill",
      "mic.coach",
      "mic.alertTone",
      "captions.mode",
      "captions.lines",
      "captions.linger",
      "captions.showUser",
      "captions.position",
    ],
  },
  {
    id: "controls",
    title: "Controls",
    paths: ["controls.mute", "controls.end", "controls.minimise", "controls.devices", "controls.language"],
  },
  {
    id: "look",
    title: "Look",
    paths: ["theme.brand", "theme.scheme", "theme.background", "theme.ink", "theme.radius", "theme.font", "dir"],
  },
];

export const MORE_GROUP = { id: "more", title: "More" } as const;

const HEX = "^#[0-9a-fA-F]{6}$";

function words(key: string): string {
  const spaced = key.replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function labelFor(path: string): string {
  return LABELS[path] ?? words(path.split(".").at(-1) ?? path);
}

/** The step a slider takes across `min`..`max`. */
function stepFor(node: SchemaNode): number {
  if (node.type === "integer") return 1;
  const span = (node.maximum ?? 0) - (node.minimum ?? 0);
  return span > 200 ? 8 : 1;
}

function leafOf(path: string, node: SchemaNode, dependsOn: string | undefined): Leaf {
  const base = {
    path,
    label: labelFor(path),
    ...(node.description ? { description: node.description } : {}),
    ...(node.default !== undefined ? { default: node.default } : {}),
    ...(dependsOn ? { dependsOn } : {}),
  };
  if (node.enum) return { ...base, kind: "choice", options: node.enum.map(String) };
  if (node.type === "boolean") return { ...base, kind: "switch" };
  if (node.type === "string" && node.pattern === HEX) return { ...base, kind: "colour" };
  if (node.type === "string") return { ...base, kind: "text", ...(node.maxLength ? { maxLength: node.maxLength } : {}) };
  if (node.type === "number" || node.type === "integer") {
    if (node.minimum !== undefined && node.maximum !== undefined) {
      return { ...base, kind: "slider", min: node.minimum, max: node.maximum, step: stepFor(node) };
    }
    return { ...base, kind: "number" };
  }
  if (node.type === "array") return { ...base, kind: "list" };
  if (node.oneOf) {
    // A number or an object of per-axis numbers (the offset): the number is what a form sets.
    const num = node.oneOf.find((b) => b.type === "number");
    if (num && node.oneOf.every((b) => b === num || b.type === "object")) {
      const merged: SchemaNode = { ...num, default: node.default };
      return leafOf(path, merged, dependsOn);
    }
    // A URL-or-colour value: the avatar's background.
    if (node.oneOf.some((b) => b.properties?.url)) return { ...base, kind: "background" };
    // A duration as text or milliseconds (the linger): text covers both.
    if (node.oneOf.some((b) => b.type === "string")) return { ...base, kind: "text" };
  }
  return { ...base, kind: "json" };
}

/** Every control the schema asks for, in schema order. */
export function leavesOf(schema: SchemaNode): Leaf[] {
  const out: Leaf[] = [];
  const walk = (node: SchemaNode, prefix: string, dependsOn: string | undefined): void => {
    for (const [key, child] of Object.entries(node.properties ?? {})) {
      const path = prefix ? `${prefix}.${key}` : key;
      // `false | {…}`: a switch for the object being there, then its fields.
      const objectBranch = child.oneOf?.find((b) => b.type === "object" && b.properties);
      if (child.oneOf?.some((b) => b.const === false) && objectBranch) {
        out.push({ path, kind: "presence", label: labelFor(path), ...(child.description ? { description: child.description } : {}), default: true });
        walk(objectBranch, path, path);
        continue;
      }
      if (child.type === "object" && child.properties) {
        walk(child, path, dependsOn);
        continue;
      }
      out.push(leafOf(path, child, dependsOn));
    }
  };
  walk(schema, "", undefined);
  return out;
}

/** The leaves in their groups, with "More" last for whatever no group names. */
export function groupLeaves(leaves: readonly Leaf[]): { id: string; title: string; leaves: Leaf[] }[] {
  const byPath = new Map(leaves.map((l) => [l.path, l]));
  const placed = new Set<string>();
  const groups = GROUPS.map((g) => {
    const mine: Leaf[] = [];
    for (const p of g.paths) {
      const leaf = byPath.get(p);
      if (leaf) {
        mine.push(leaf);
        placed.add(p);
      }
    }
    return { id: g.id, title: g.title, leaves: mine };
  }).filter((g) => g.leaves.length > 0);
  const rest = leaves.filter((l) => !placed.has(l.path));
  if (rest.length > 0) groups.push({ id: MORE_GROUP.id, title: MORE_GROUP.title, leaves: rest });
  return groups;
}

// ------------------------------------------------------------ sparse config

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Sparse = { [key: string]: Json };

/** The value at `path` in a configuration, or undefined. */
export function getPath(config: Sparse, path: string): Json | undefined {
  let node: Json | undefined = config;
  for (const key of path.split(".")) {
    if (node === null || typeof node !== "object" || Array.isArray(node)) return undefined;
    node = node[key];
  }
  return node;
}

/**
 * A copy of `config` with `path` set to `value`, or removed when `value` is
 * undefined. Objects left empty by a removal go too, so the configuration
 * stays the smallest one that says what was changed.
 */
export function setPath(config: Sparse, path: string, value: Json | undefined): Sparse {
  const keys = path.split(".");
  const copy = structuredClone(config);
  // Setting a field under `false` (a voice-only avatar) turns the face back on.
  const parents: Sparse[] = [copy];
  let node: Sparse = copy;
  for (const key of keys.slice(0, -1)) {
    const next = node[key];
    if (next === null || typeof next !== "object" || Array.isArray(next)) {
      if (value === undefined) return copy;
      node[key] = {};
    }
    node = node[key] as Sparse;
    parents.push(node);
  }
  const last = keys.at(-1) as string;
  if (value === undefined) delete node[last];
  else node[last] = value;
  // Remove objects the removal emptied, deepest first.
  for (let i = keys.length - 1; i > 0; i--) {
    const parent = parents[i - 1] as Sparse;
    const key = keys[i - 1] as string;
    const child = parent[key];
    if (child && typeof child === "object" && !Array.isArray(child) && Object.keys(child).length === 0) delete parent[key];
  }
  return copy;
}

/** The value a control shows: what was set, else the schema's default. */
export function shownValue(config: Sparse, leaf: Leaf): Json | undefined {
  if (leaf.kind === "presence") return getPath(config, leaf.path) !== false;
  if (leaf.dependsOn && getPath(config, leaf.dependsOn) === false) return leaf.default as Json | undefined;
  const set = getPath(config, leaf.path);
  return set !== undefined ? set : (leaf.default as Json | undefined);
}

/**
 * Set a leaf from what its control holds. A value equal to the default is
 * removed instead, so the configuration names only real changes.
 */
export function applyLeaf(config: Sparse, leaf: Leaf, value: Json | undefined): Sparse {
  if (leaf.kind === "presence") return value === false ? setPath(config, leaf.path, false) : setPath(config, leaf.path, undefined);
  const isDefault = value === undefined || value === "" || JSON.stringify(value) === JSON.stringify(leaf.default);
  return setPath(config, leaf.path, isDefault ? undefined : value);
}
