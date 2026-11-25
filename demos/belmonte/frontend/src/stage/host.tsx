/**
 * Stage, attached once for the whole app, inside the router: it lives as long
 * as the call, hears every route change, registers a performer for every move
 * the spec declares (performers navigate the SPA themselves, so none of them
 * depends on which page is up), and sends each change as the `stay`
 * slice's event — `by: "agent"` with the move's call_ref while a move runs
 * (and Stage's short window after it), `by: "visitor"` otherwise.
 */
import * as React from "react";
import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { type ArgsOf, type MoveId, type Performer } from "@voqalize/stage";
import { stageHooks } from "@voqalize/stage/react";
import { setReporter } from "../state/store";
import { useVoiceClient } from "./client";
import { setNavigate } from "./nav";
import { performers } from "./performers";
import { scene } from "./scene.gen";

const { useStage, useMove, useNavigated } = stageHooks(React);
type Spec = typeof scene.spec;

export const SPOTLIGHT = { color: "#b8873e", width: 3, radius: 14, glow: "rgba(184,135,62,0.3)", pad: 4 };

function Register<K extends MoveId<Spec>>({ stage, id }: { stage: ReturnType<typeof useStage<Spec>>; id: K }) {
  useMove(stage, id, performers[id] as unknown as Performer<ArgsOf<Spec, K>>);
  return null;
}

/** Call once, inside the router. */
export function StageHost() {
  const client = useVoiceClient((s) => s.client);
  const stage = useStage(client, scene, { theme: SPOTLIGHT });
  const location = useLocation();
  const nav = useNavigate();
  useEffect(() => {
    setNavigate((p) => nav(p));
    return () => setNavigate(null);
  }, [nav]);
  useNavigated(stage, location.pathname);
  useEffect(() => {
    if (!stage) return;
    setReporter(([id, data]) => {
      const agent = stage.agent && Date.now() <= stage.agent.until ? stage.agent : null;
      stage.page.send(scene.event(id as never, data as never, agent ? { by: "agent", callRef: agent.callRef } : { by: "visitor" }));
    });
    return () => setReporter(null);
  }, [stage]);
  return (
    <>
      {scene.spec.moves.map((m) => (
        <Register key={m.id} stage={stage} id={m.id as MoveId<Spec>} />
      ))}
    </>
  );
}
