/**
 * `?debug=1`: the moves, reachable without a call. `window.__bankMove(id, args)`
 * runs a move through the same Stage the brain's moves go through
 * (`stage.moves.run`), so it rings, refuses and answers exactly as on a call,
 * and resolves to the StageResult. Stage exists only with a client; in debug
 * mode without voice the dock puts a stand-in client in the seam
 * (VoiceDock.tsx), so it is there either way.
 */
import { useEffect } from "react";
import type { StageResult } from "@voqalize/stage";
import { useAppStage } from "../stage/host";
import { debugMode } from "./events";

let n = 0;

export async function runMove(id: string, args: unknown): Promise<StageResult | null | { error: string }> {
  const stage = useAppStage.getState().stage ?? (await waitForStage());
  if (!stage) return { error: "Stage is not attached (no client yet)" };
  n += 1;
  return stage.moves.run(id, args, `dbg-${n}`);
}

async function waitForStage(ms = 3000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    const s = useAppStage.getState().stage;
    if (s) return s;
    await new Promise((r) => setTimeout(r, 50));
  }
  return null;
}

export function useDebugHarness() {
  useEffect(() => {
    if (!debugMode()) return;
    const w = window as unknown as { __bankMove?: typeof runMove };
    w.__bankMove = runMove;
    return () => {
      delete w.__bankMove;
    };
  }, []);
}
