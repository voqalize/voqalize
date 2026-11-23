/**
 * The agent's dock. With an agent configured it is the live call (loaded only
 * then, so a site without voice never downloads the client); without one it
 * says so plainly, and every surface the agent would drive still works by hand.
 */
import { Suspense, lazy } from "react";
import { demo } from "../config";
import { PERSONA } from "../persona";
import { actions } from "../state/store";
import { DockView } from "./DockView";
import { endFakeCall, useFakeCall } from "./fakeCall";

export { useFakeCall };

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

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
      muted={fake.muted}
      disabled
      disabledNote={fake.state === "idle" ? (loading ? "Getting ready…" : "Voice is off in this preview") : undefined}
      onStart={() => undefined}
      onMute={() => useFakeCall.setState({ muted: !fake.muted })}
      onEnd={endFakeCall}
      onLanguage={(code) => actions.setLang(code)}
      face={
        <div className="face-placeholder" aria-hidden>
          <span>{PERSONA.display_name.slice(0, 1)}</span>
        </div>
      }
    />
  );
}
