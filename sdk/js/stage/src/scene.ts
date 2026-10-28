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

import type { MoveClass, Moves, Performer } from "./moves";

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

/** An app's Stage Spec (`stage.schema.json`). */
export interface SceneSpec {
  readonly $schema?: string;
  readonly stage: 1;
  readonly id: string;
  readonly languages?: readonly string[];
  readonly moves: readonly MoveSpec[];
}

type ScalarOf<A> = A extends { readonly enum: readonly (infer L)[] }
  ? L
  : A extends { readonly type: "integer" | "number" }
    ? number
    : A extends { readonly type: "boolean" }
      ? boolean
      : string;

type ValueOf<A extends ArgSpec> = A extends { readonly type: "array" }
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
  };
}
