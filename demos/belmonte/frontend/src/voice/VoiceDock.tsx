/**
 * The concierge's one entry point (`Widget`): a circle with her face, which a
 * tap expands to Talk before a call, and to Mute and End during one. No
 * transcript anywhere.
 *
 * With an agent configured the call is live (pipecat is loaded only then);
 * without one the widget says so and every screen works by hand. With
 * `?debug=1` the console can fake a call to show the in-call widget.
 */
import { Suspense, lazy } from "react";
import { demo } from "../config";
import { Face } from "./Face";
import { useFakeCall } from "./fake";
import { Widget } from "./Widget";

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

export function VoiceDock() {
  if (!voiceReady()) return <DockPlaceholder />;
  return (
    <Suspense fallback={<DockPlaceholder loading />}>
      <VoiceCall />
    </Suspense>
  );
}

function DockPlaceholder({ loading = false }: { loading?: boolean }) {
  const fake = useFakeCall();
  return (
    <Widget
      live={fake.on}
      state={fake.state}
      muted={fake.muted}
      onMute={() => useFakeCall.setState({ muted: !fake.muted })}
      onEnd={() => useFakeCall.setState({ on: false })}
      talkDisabled
      talkTitle="Voice is not switched on for this preview"
      status={loading ? "Getting ready…" : null}
    >
      <Face live={false} avatar={() => null} />
    </Widget>
  );
}
