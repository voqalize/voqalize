/**
 * The agent's dock. With an agent configured it is the live call (loaded only
 * then, so a site without voice never downloads the client); without one it
 * says so plainly, and every surface the agent would drive still works by hand.
 */
import { Suspense, lazy } from "react";
import { create } from "zustand";
import { demo } from "../config";
import { actions } from "../state/store";
import { type CallState, DockView } from "./DockView";

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

/** A call, faked for the `?debug=1` console: the live look without a client. */
export const useFakeCall = create<{ state: CallState; heard: string }>(() => ({ state: "idle", heard: "" }));

export function VoiceDock() {
  if (!voiceReady()) return <Placeholder />;
  return (
    <Suspense fallback={<Placeholder loading />}>
      <VoiceCall />
    </Suspense>
  );
}

function Placeholder({ loading = false }: { loading?: boolean }) {
  const fake = useFakeCall();
  return (
    <DockView
      state={fake.state}
      heard={fake.heard}
      muted={false}
      disabled
      disabledNote={fake.state === "idle" ? (loading ? "Getting ready…" : "Voice is off in this preview") : undefined}
      onStart={() => undefined}
      onMute={() => undefined}
      onEnd={() => useFakeCall.setState({ state: "idle", heard: "" })}
      onLanguage={(code) => actions.setLang(code)}
      face={<div className="agent-face-fallback" aria-hidden />}
    />
  );
}
