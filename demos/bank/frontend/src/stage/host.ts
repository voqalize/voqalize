/**
 * Stage, attached once for the whole app, above the router outlet: it lives as
 * long as the call does and hears every route change through `useNavigated`.
 * Performers are registered in `src/stage/performers*.ts` with `useMove`, from
 * the app shell, so a move works from any page (it navigates first when it must).
 */
import * as React from "react";
import { useEffect } from "react";
import { stageHooks } from "@voqalize/stage/react";
import { create } from "zustand";
import { useVoiceClient } from "./client";
import { scene } from "./scene.gen";
import { withWhole } from "./view";

const hooks = stageHooks(React);
export const { useStage, useSlice, useNavigated } = hooks;

/**
 * Stage's `useMove`, with every performer's `c.scrollTo` and `c.ring` showing
 * the target's whole group first, inner scroll areas included (X1, `view.ts`).
 */
export const useMove: typeof hooks.useMove = (stage, id, performer) =>
  hooks.useMove(stage, id, (args, c) => performer(args, withWhole(c)));

export type AppStage = ReturnType<typeof useStage<typeof scene.spec>>;
export const useAppStage = create<{ stage: AppStage }>(() => ({ stage: null }));

/** Call once, in the app shell. */
export function useStageHost(path: string): AppStage {
  const client = useVoiceClient((s) => s.client);
  const stage = useStage(client, scene, { theme: { color: "#E8A33D" } });
  useEffect(() => useAppStage.setState({ stage }), [stage]);
  useNavigated(stage, path);
  return stage;
}
