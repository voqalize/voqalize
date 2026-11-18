import { Suspense, lazy, useState } from "react";
import { demo } from "../config";
import { PERSONA } from "../data/persona";
import { Dock, FacePlaceholder } from "./Dock";

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

/**
 * The dock. With an agent configured it is the live call (pipecat loads only
 * then); without one it still shows, and says plainly that voice is off in
 * this build. Every page works by click alone either way.
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
  const [said, setSaid] = useState<string | null>(null);
  return (
    <Dock
      face={<FacePlaceholder />}
      activity="idle"
      status={loading ? "Getting ready…" : (said ?? PERSONA.role)}
      muted={false}
      onCall={() => setSaid("Voice is not configured in this build")}
      onMute={() => {}}
      onEnd={() => {}}
    />
  );
}
