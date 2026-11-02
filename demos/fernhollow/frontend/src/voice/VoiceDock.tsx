import { Mic } from "lucide-react";
import { Suspense, lazy } from "react";
import { demo } from "../config";

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

/**
 * Mira's dock, bottom centre. With an agent configured it is the live call;
 * without one it says so plainly, and every surface she would drive still
 * works by hand.
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
  return (
    <div className="dock is-off" role="region" aria-label="Talk to Mira">
      <div className="dock-face dock-face-placeholder" aria-hidden>
        <span>M</span>
      </div>
      <div className="dock-text">
        <p className="dock-name">Mira</p>
        <p className="dock-status">{loading ? "Getting ready…" : "Voice coming soon"}</p>
      </div>
      <button type="button" className="dock-cta" disabled title="Voice is not switched on for this preview">
        <Mic size={16} /> Talk to Mira
      </button>
    </div>
  );
}
