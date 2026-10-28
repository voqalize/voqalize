/**
 * `@voqalize/stage/react`: Stage's lifecycle in a React app, in a few hooks.
 *
 * It is glue, not a wrapper: the app keeps its own pipecat client (for
 * example `usePipecatClient()`), and these hooks only attach Stage to it,
 * register the app's performers and turn its state changes into the events
 * its spec declares. The app hands React in, so this package never imports a
 * copy of React of its own, and no two copies ever meet:
 *
 * ```tsx
 * import * as React from "react";
 * import { stageHooks } from "@voqalize/stage/react";
 * import { scene } from "./stage/scene.gen";
 *
 * const { useStage, useMove, useSlice, useNavigated } = stageHooks(React);
 *
 * function Shop() {
 *   const stage = useStage(usePipecatClient(), scene);
 *   useMove(stage, "commerce.sort", async ({ order }, c) => {
 *     await c.ring(sortControl.current!);
 *     setSort(order);
 *     return `sorted by ${order}`;
 *   });
 *   useSlice(stage, listing, (prev, next) =>
 *     prev && prev.sort !== next.sort ? ["listing.sorted", next] : null);
 *   useNavigated(stage, location.pathname);
 * }
 * ```
 *
 * A change the app makes inside a performer, or within
 * {@link AGENT_WINDOW_MS} of one finishing, is reported `by: "agent"` with the
 * move's `call_ref`; anything else is the visitor's.
 */

import type { StageClient } from "./attach";
import { Moves, type Performer } from "./moves";
import { type StagePage, stagePage } from "./page";
import type { ArgsOf, EventData, EventId, MoveId, Scene, SceneSpec } from "./scene";
import { Spotlight, type SpotlightTheme } from "./spotlight";

/** The hooks this glue uses: any React from 18 on has them. */
export interface ReactHooks {
  useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
  useRef<T>(initial: T): { current: T };
  useState<T>(initial: T): [T, (value: T) => void];
}

/** A state change this soon after the agent's move finished is the move's. */
export const AGENT_WINDOW_MS = 500;

/** Stage, attached to the app's client. */
export interface AppStage<S extends SceneSpec> {
  readonly scene: Scene<S>;
  readonly moves: Moves;
  readonly page: StagePage;
  /** The agent's move in progress, or just finished: whose a change is. */
  readonly agent: { callRef: string; until: number } | null;
}

export interface UseStageOptions {
  theme?: SpotlightTheme;
  lang?: string;
}

export function stageHooks(React: ReactHooks) {
  /** Stage on `client` while the component is mounted; `null` until there is a client. */
  function useStage<S extends SceneSpec>(
    client: StageClient | null | undefined,
    scene: Scene<S>,
    opts: UseStageOptions = {},
  ): AppStage<S> | null {
    const [stage, setStage] = React.useState<AppStage<S> | null>(null);
    React.useEffect(() => {
      if (!client) return;
      const moves = new Moves(new Spotlight(opts.theme ?? { color: "#2563eb" }));
      const page = stagePage(client, moves, { lang: opts.lang });
      const made: { -readonly [K in keyof AppStage<S>]: AppStage<S>[K] } = { scene, moves, page, agent: null };
      setStage(made);
      return () => {
        page.detach();
        setStage(null);
      };
    }, [client, scene]);
    return stage;
  }

  /** Perform a move the spec declares, with the latest render's closure. */
  function useMove<S extends SceneSpec, K extends MoveId<S>>(
    stage: AppStage<S> | null,
    id: K,
    performer: Performer<ArgsOf<S, K>>,
  ): void {
    const latest = React.useRef<Performer<ArgsOf<S, K>> | null>(performer);
    latest.current = performer;
    React.useEffect(() => {
      if (!stage) return;
      const live = stage as { agent: AppStage<S>["agent"] };
      stage.scene.register(stage.moves, id, async (args, c) => {
        const run = latest.current;
        if (!run) return c.refuse("move", "that part of the app is not on screen");
        live.agent = { callRef: c.callRef, until: Number.POSITIVE_INFINITY };
        try {
          return await run(args, c);
        } finally {
          live.agent = { callRef: c.callRef, until: Date.now() + AGENT_WINDOW_MS };
        }
      });
      return () => {
        latest.current = null;
      };
    }, [stage, id]);
  }

  /**
   * Turn a change of `value` into the event the spec declares for it:
   * `toEvent(prev, next)` names it and its data, or says `null` (nothing the
   * agent needs to hear). Only what the slice declares is sent.
   */
  function useSlice<S extends SceneSpec, T, E extends EventId<S>>(
    stage: AppStage<S> | null,
    value: T,
    toEvent: (prev: T | undefined, next: T) => readonly [E, EventData<S, E>] | null,
  ): void {
    const prev = React.useRef<T | undefined>(undefined);
    React.useEffect(() => {
      const before = prev.current;
      prev.current = value;
      if (!stage) return;
      const named = toEvent(before, value);
      if (!named) return;
      const agent = stage.agent && Date.now() <= stage.agent.until ? stage.agent : null;
      stage.page.send(
        stage.scene.event(named[0], named[1], agent ? { by: "agent", callRef: agent.callRef } : { by: "visitor" }),
      );
    }, [stage, value]);
  }

  /** The route changed: the agent hears where the page is now. */
  function useNavigated(stage: AppStage<SceneSpec> | null, path: string): void {
    const first = React.useRef(true);
    React.useEffect(() => {
      if (!stage) return;
      if (first.current) {
        first.current = false;
        return;
      }
      stage.page.hello();
    }, [stage, path]);
  }

  return { useStage, useMove, useSlice, useNavigated };
}
