import { Suspense, lazy } from "react";
import { create } from "zustand";
import { demo } from "../config";
import { type CallState, Dock, FacePlaceholder } from "./Dock";

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

/** A call faked by the `?debug=1` console, so the connected look can be screenshotted. */
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
    <Dock
      state={fake.state}
      heard={fake.heard}
      muted={false}
      disabled
      note={fake.state === "idle" ? (loading ? "Getting ready…" : "Voice is off in this preview") : null}
      face={<FacePlaceholder />}
      onStart={() => undefined}
      onMute={() => undefined}
      onEnd={() => useFakeCall.setState({ state: "idle", heard: "" })}
    />
  );
}
