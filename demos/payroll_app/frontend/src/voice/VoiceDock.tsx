/**
 * The guide's dock, bottom right. With an agent configured it is the live
 * call (loaded lazily, so a build without voice never downloads it); without
 * one the dock says so and every screen works by hand.
 */
import { Mic } from "lucide-react";
import { Suspense, lazy } from "react";
import { demo } from "../config";
import { PERSONA } from "../persona";
import { LangToggle } from "./LangToggle";

const VoiceCall = lazy(() => import("./VoiceCall"));

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
  return (
    <div className="dock is-off" role="region" aria-label={`Talk to ${PERSONA.display_name}`}>
      <div className="dock-face" aria-hidden>
        <span className="face-initial">{PERSONA.display_name.charAt(0)}</span>
      </div>
      <div className="dock-text">
        <p className="dock-name">{PERSONA.display_name}</p>
        <p className="dock-status">{loading ? "Getting ready…" : "Voice is off in this preview"}</p>
      </div>
      <LangToggle />
      <button type="button" className="dock-cta" disabled title="Voice is not switched on for this preview">
        <Mic size={16} aria-hidden /> <span className="dock-cta-label">Talk to {PERSONA.display_name}</span>
      </button>
    </div>
  );
}
