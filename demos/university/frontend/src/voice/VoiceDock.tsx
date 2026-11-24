import { Suspense, lazy } from "react";
import { demo } from "../config";
import { CallTile } from "./CallTile";
import { DockBar } from "./Dock";
import { Face } from "./Face";
import { useFakeCall } from "./fake";

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

/**
 * The dock. With an agent configured it is the live call (pipecat and the
 * avatar runtime load only then); without one it still shows, and says
 * plainly that voice is off in this build. Every page works by click alone
 * either way. `?debug=1` can fake a call either way (`useFakeCall`).
 */
export function VoiceDock() {
  if (!voiceReady()) return <NoVoiceDock />;
  return (
    <Suspense fallback={<NoVoiceDock loading />}>
      <VoiceCall />
    </Suspense>
  );
}

function NoVoiceDock({ loading = false }: { loading?: boolean }) {
  const fake = useFakeCall();
  return (
    <>
      <CallTile
        live={fake.on}
        state={fake.state}
        muted={fake.muted}
        onMute={() => useFakeCall.setState({ muted: !fake.muted })}
        onEnd={() => useFakeCall.setState({ on: false })}
      >
        <Face live={false} avatar={() => null} />
      </CallTile>
      <DockBar
        calling={fake.on}
        activity={fake.on ? "listening" : "idle"}
        status={loading ? "Getting ready…" : null}
        disabled
        title="Voice is not switched on in this build"
      />
    </>
  );
}
