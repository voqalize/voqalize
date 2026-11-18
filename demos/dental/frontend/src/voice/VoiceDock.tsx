import { Mic } from "lucide-react";
import { Suspense, lazy } from "react";
import { Avatar } from "@voqalize/avatar/react";
import { demo } from "../config";
import { displayName, persona } from "../persona";
import { LangToggle } from "../components/LangToggle";
import { CallTile } from "./CallTile";
import { useFakeCall } from "./fake";
import { useDockMode } from "./useDockMode";
import { callLabel } from "./label";
import { useStore } from "../state/store";

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

/**
 * The front desk's dock, bottom centre. With an agent configured it is the
 * live call; without one it says so plainly, and every page still works by hand.
 */
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
  const mode = useDockMode(fake.on);
  const lang = useStore((s) => s.lang);
  return (
    <>
      <CallTile
        live={fake.on}
        state={fake.state}
        heard={fake.heard}
        muted={fake.muted}
        onMute={() => useFakeCall.setState({ muted: !fake.muted })}
        onEnd={() => useFakeCall.setState({ on: false, heard: "" })}
      >
        <span className="face-initial" aria-hidden>
          {displayName.slice(0, 1)}
        </span>
        <Avatar className="dock-avatar" character={persona.character} aria-label={displayName} />
      </CallTile>
      <div className={`dock is-off${fake.on ? " is-calling" : ""}${mode.classes}`} role="region" aria-label={callLabel(lang)}>
        <div className="dock-face dock-face-slot" aria-hidden />
        <div className="dock-text">
          <p className="dock-name">{displayName}</p>
          <p className="dock-status">{loading ? "Getting ready…" : fake.on ? "Listening" : "Voice preview is off"}</p>
        </div>
        <LangToggle compact />
        <button type="button" className="dock-cta" disabled title="Voice is not switched on for this preview">
          <Mic size={16} /> <span className="dock-cta-label">{callLabel(lang)}</span>
        </button>
      </div>
    </>
  );
}
