/**
 * Stage, attached once for the whole app, above the router outlet: it lives
 * as long as the call does and hears every route change through
 * `useNavigated`. Every performer is registered once, globally, from
 * `performers.ts` — a performer opens the page it needs itself, so no move
 * depends on which page happens to be in front.
 */
import * as React from "react";
import { useEffect } from "react";
import { stageHooks } from "@voqalize/stage/react";
import { useVoiceClient } from "./client";
import { performers } from "./performers";
import { scene } from "./scene.gen";
import { STAGE_THEME } from "./theme";

export const { useStage, useNavigated } = stageHooks(React);

/** Call once, in the app shell. */
export function useStageHost(path: string) {
  const client = useVoiceClient((s) => s.client);
  const stage = useStage(client, scene, { theme: STAGE_THEME });
  useEffect(() => {
    if (stage) scene.registerAll(stage.moves, performers());
  }, [stage]);
  useNavigated(stage, path);
}
