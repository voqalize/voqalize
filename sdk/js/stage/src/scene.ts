/**
 * A Stage Spec on the page: the moves an app declares, with every move's
 * argument type inferred from the declaration.
 *
 * A spec is written once, as data (`scene.json`, or a `defineScene({...})`
 * literal), and the brain and the page both read it, so a move's id, class and
 * arguments are never written twice:
 *
 * ```ts
 * export const scene = defineScene({
 *   stage: 1,
 *   id: "shop",
 *   moves: [
 *     { id: "core.show", verb: "show", class: "look", args: [{ name: "target" }] },
 *     { id: "shop.open", class: "navigate", args: [{ name: "path" }, { name: "tab", optional: true }] },
 *   ],
 * });
 *
 * scene.register(moves, "shop.open", async (a, c) => {   // a: { path: string; tab?: string | null }
 *   ...
 * });
 * ```
 *
 * `voqalize stage gen --ts` writes the same call from a `scene.json`.
 */

import type { MoveClass, Moves, Performer } from "./moves.js";
import type { PluginSpec } from "./plugins.js";
import type { StageEvent } from "./wire.gen.js";

type Scalar = "string" | "integer" | "number" | "boolean";

/** What an array argument holds. */
export interface ItemSpec {
  readonly type?: Scalar;
  readonly enum?: readonly string[];
}

/** One argument of a move, in the order a cue gives them. */
export interface ArgSpec {
  readonly name: string;
  readonly type?: Scalar | "array";
  readonly items?: ItemSpec;
  readonly enum?: readonly string[];
  /** May be left out, or `null`. */
  readonly optional?: boolean;
  /** What it is when left out. */
  readonly default?: string | number | boolean;
  readonly doc?: string;
}

/** One move. The brain's own fields (claims, objects, its prompt line) may be
 *  here too; the page ignores them. */
export interface MoveSpec {
  readonly id: string;
  readonly verb?: string | null;
  readonly class: MoveClass;
  readonly args?: readonly ArgSpec[];
  readonly say?: string;
  readonly claims?: readonly string[];
  readonly objects?: readonly string[];
  readonly doc?: string;
  readonly notes?: readonly string[];
}

/** One field of a slice. A `private` one is stripped here, before anything is sent. */
export interface FieldSpec {
  readonly name: string;
  readonly type?: Scalar | "array" | "object";
  readonly items?: ItemSpec;
  readonly fields?: readonly FieldSpec[];
  readonly enum?: readonly string[];
  readonly optional?: boolean;
  readonly private?: boolean;
  readonly doc?: string;
}

/** A named, typed piece of the page's state, kept in the brain's mirror. */
export interface SliceSpec {
  readonly id: string;
  readonly fields: readonly FieldSpec[];
  readonly window?: number;
  readonly doc?: string;
}

/** A named act that changes one slice. */
export interface EventSpec {
  readonly id: string;
  readonly slice: string;
  readonly op?: "set" | "merge" | "clear";
  readonly note?: string;
  readonly doc?: string;
}

/** An app's Stage Spec (`stage.schema.json`). */
export interface SceneSpec {
  readonly $schema?: string;
  readonly stage: 1;
  readonly id: string;
  readonly languages?: readonly string[];
  readonly moves: readonly MoveSpec[];
  readonly slices?: readonly SliceSpec[];
  readonly events?: readonly EventSpec[];
  /** The kits taken; their parts are already merged into the lists above. */
  readonly kits?: readonly { readonly id: string; readonly major: number; readonly moves?: readonly string[] }[];
  readonly plugins?: readonly PluginSpec[];
}

type ScalarOf<A> = A extends { readonly enum: readonly (infer L)[] }
  ? L
  : A extends { readonly type: "integer" | "number" }
    ? number
    : A extends { readonly type: "boolean" }
      ? boolean
      : string;

type ValueOf<A> = A extends { readonly type: "array" }
  ? A extends { readonly items: infer I }
    ? ScalarOf<I>[]
    : string[]
  : ScalarOf<A>;

type Needed<A> = A extends { readonly optional: true } ? false : A extends { readonly default: unknown } ? false : true;

type Simplify<T> = { [K in keyof T]: T[K] } & {};

type ArgsFrom<As extends readonly ArgSpec[]> = Simplify<
  { [A in As[number] as Needed<A> extends true ? A["name"] : never]: ValueOf<A> } & {
    [A in As[number] as Needed<A> extends true ? never : A["name"]]?:
      | ValueOf<A>
      | (A extends { readonly optional: true } ? null : never);
  }
>;

/** The ids of a spec's moves. */
export type MoveId<S extends SceneSpec> = S["moves"][number]["id"];

/** The arguments a move's performer gets, from its declaration. */
export type ArgsOf<S extends SceneSpec, K extends MoveId<S>> =
  Extract<S["moves"][number], { readonly id: K }> extends { readonly args: infer As extends readonly ArgSpec[] }
    ? ArgsFrom<As>
    : Record<never, never>;

type FieldValue<F extends FieldSpec> = F extends { readonly fields: infer Fs extends readonly FieldSpec[] }
  ? F extends { readonly type: "array" }
    ? FieldsOf<Fs>[]
    : FieldsOf<Fs>
  : ValueOf<F>;

/** What a page sends for these fields: private ones are left out of the type. */
type FieldsOf<Fs extends readonly FieldSpec[]> = Simplify<
  {
    [F in Fs[number] as F extends { readonly private: true }
      ? never
      : F extends { readonly optional: true }
        ? never
        : F["name"]]: FieldValue<F>;
  } & {
    [F in Fs[number] as F extends { readonly private: true }
      ? never
      : F extends { readonly optional: true }
        ? F["name"]
        : never]?: FieldValue<F> | null;
  }
>;

type Events<S extends SceneSpec> = S extends { readonly events: readonly (infer E)[] } ? E : never;
type Slices<S extends SceneSpec> = S extends { readonly slices: readonly (infer L)[] } ? L : never;

/** The ids of a spec's events. */
export type EventId<S extends SceneSpec> = Events<S> extends { readonly id: infer I extends string } ? I : never;

/** A slice's value, as the page reports it. */
export type SliceOf<S extends SceneSpec, L extends string> =
  Extract<Slices<S>, { readonly id: L }> extends { readonly fields: infer Fs extends readonly FieldSpec[] }
    ? FieldsOf<Fs>
    : never;

/** What an event carries: the slice's value (`set`), what changed (`merge`,
 *  the default), or nothing (`clear`). */
export type EventData<S extends SceneSpec, E extends EventId<S>> =
  Extract<Events<S>, { readonly id: E }> extends infer D extends EventSpec
    ? D extends { readonly op: "clear" }
      ? Record<never, never>
      : D extends { readonly op: "set" }
        ? SliceOf<S, D["slice"]>
        : Partial<SliceOf<S, D["slice"]>>
    : never;

/** A performer for every move of a spec, by id. */
export type Performers<S extends SceneSpec> = { [K in MoveId<S>]: Performer<ArgsOf<S, K>> };

export interface Scene<S extends SceneSpec> {
  readonly spec: S;
  /** The declaration of the move with this id. */
  move<K extends MoveId<S>>(id: K): Extract<S["moves"][number], { readonly id: K }>;
  /** Register the performer for one move, with the class and a cue's argument
   *  names its declaration gives. */
  register<K extends MoveId<S>>(moves: Moves, id: K, performer: Performer<ArgsOf<S, K>>): void;
  /** Register a performer for every move the spec declares: one left out is a
   *  compile error. */
  registerAll(moves: Moves, performers: Performers<S>): void;
  /** A state event to send (`Attached.send`): only the fields the slice
   *  declares, and none it marks private, whatever `data` holds. */
  event<E extends EventId<S>>(
    id: E,
    data: EventData<S, E>,
    opts?: { by?: "visitor" | "agent"; callRef?: string },
  ): StageEvent;
}

function keep(fields: readonly FieldSpec[], data: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    if (f.private || !(f.name in data)) continue;
    let v = data[f.name];
    if (f.fields && Array.isArray(v)) {
      v = v.filter((x): x is Record<string, unknown> => !!x && typeof x === "object").map((x) => keep(f.fields!, x));
    } else if (f.fields && v && typeof v === "object") {
      v = keep(f.fields, v as Record<string, unknown>);
    }
    out[f.name] = v;
  }
  return out;
}

/** A Stage Spec, kept as written so every move's argument type is inferred.
 *  Throws on a spec that declares one id twice. */
export function defineScene<const S extends SceneSpec>(spec: S): Scene<S> {
  const byId = new Map<string, MoveSpec>();
  for (const m of spec.moves) {
    if (byId.has(m.id)) throw new Error(`scene ${spec.id}: two moves have the id ${m.id}`);
    byId.set(m.id, m);
  }
  const declared = (id: string): MoveSpec => {
    const m = byId.get(id);
    if (!m) throw new Error(`scene ${spec.id} declares no move ${id}`);
    return m;
  };
  const register = (moves: Moves, id: string, performer: Performer<never>): void => {
    const m = declared(id);
    const params = m.verb ? m.args?.map((a) => a.name) : undefined;
    moves.register(id, m.class, performer, params ? { params } : {});
  };
  return {
    spec,
    move: (id) => declared(id) as never,
    register: (moves, id, performer) => register(moves, id, performer as Performer<never>),
    registerAll(moves, performers) {
      for (const m of spec.moves) register(moves, m.id, performers[m.id as MoveId<S>] as Performer<never>);
    },
    event(id, data, opts = {}) {
      const ev = spec.events?.find((e) => e.id === id);
      if (!ev) throw new Error(`scene ${spec.id} declares no event ${id}`);
      const slice = spec.slices?.find((s) => s.id === ev.slice);
      if (!slice) throw new Error(`scene ${spec.id} declares no slice ${ev.slice}`);
      const out: StageEvent = {
        name: id,
        by: opts.by ?? "visitor",
        data: ev.op === "clear" ? {} : keep(slice.fields, data as Record<string, unknown>),
      };
      if (opts.callRef) out.call_ref = opts.callRef;
      return out;
    },
  };
}
