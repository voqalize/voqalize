/**
 * Stage, attached once for the whole store, above the router outlet: it
 * lives as long as the call does, hears every route change through
 * `useNavigated` (no page load ever happens), and pages register their own
 * moves on it with `useMove` while they are on screen — a move for a page that
 * is not showing is refused with "not on screen".
 */
import * as React from "react";
import { useEffect } from "react";
import { stageHooks } from "@voqalize/stage/react";
import { create } from "zustand";
import { Moves, Spotlight } from "@voqalize/stage";
import { debugMode } from "../voice/events";
import { useVoiceClient } from "./client";
import { scene } from "./scene.gen";

export const { useStage, useMove, useSlice, useNavigated } = stageHooks(React);

type AppStage = ReturnType<typeof useStage<typeof scene.spec>>;
export const useAppStage = create<{ stage: AppStage }>(() => ({ stage: null }));

/** Call once, in the app shell. */
export function useStageHost(path: string) {
  const client = useVoiceClient((s) => s.client);
  const stage = useStage(client, scene, { theme: { color: "#4b45c6" } });
  useEffect(() => {
    if (stage || !debugMode()) {
      useAppStage.setState({ stage });
      return;
    }
    // ?debug=1 with no call: the same moves on a stage with no client, so the
    // console can make them by hand (window.__fhStageMove).
    const moves = new Moves(new Spotlight({ color: "#4b45c6" }));
    useAppStage.setState({
      stage: { scene, moves, page: { send() {}, hello() {}, detach() {}, timeline: null }, agent: null } as unknown as AppStage,
    });
    let n = 0;
    (window as unknown as { __fhStageMove?: unknown }).__fhStageMove = (move: string, args: unknown) => moves.run(move, args, `dev-${++n}`);
  }, [stage]);
  useNavigated(stage, path);
}
