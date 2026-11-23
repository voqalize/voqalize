/**
 * The guide's one entry point. Idle, a pill at the bottom right: the face,
 * the name, the job on this page (persona.json `roles`), the EN / हिंदी toggle
 * and "Talk to {name}". In a call the pill goes away and the face becomes the
 * floating call tile (`CallTile`), which holds the language toggle, mute,
 * minimise and end. No transcript is shown anywhere.
 *
 * With an agent configured the call is live (loaded lazily, so a build without
 * voice never downloads it); without one the pill says so and every screen
 * works by hand. `?debug=1` can fake a call either way (`useFakeCall`).
 */
import { Mic } from "lucide-react";
import { Suspense, lazy } from "react";
import { useLocation } from "react-router-dom";
import { demo } from "../config";
import { PERSONA, roleFor } from "../persona";
import { CallTile } from "./CallTile";
import { Face } from "./Face";
import { useFakeCall } from "./fake";
import { LangToggle } from "./LangToggle";
import { useDockMode } from "./useDockMode";

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

/** The idle pill. `calling` hides it (the tile has the call); `status` replaces the role line (an error). */
export function DockBar({
  calling,
  activity,
  status,
  onTalk,
  disabled = false,
  title,
}: {
  calling: boolean;
  activity: string;
  status?: string | null;
  onTalk?: () => void;
  disabled?: boolean;
  title?: string;
}) {
  const mode = useDockMode();
  const role = roleFor(useLocation().pathname);
  return (
    <div className={`dock is-${activity}${calling ? " is-calling" : ""}${mode.classes}`} role="region" aria-label={`Talk to ${PERSONA.display_name}`} aria-hidden={calling || undefined}>
      <div className="dock-face dock-face-slot" aria-hidden />
      <div className="dock-text">
        <p className="dock-name">{PERSONA.display_name}</p>
        <p className="dock-status" aria-live="polite" title={status ?? role}>
          {status ?? role}
        </p>
      </div>
      <LangToggle />
      <button type="button" className="dock-cta" disabled={disabled} title={title} onClick={onTalk} tabIndex={calling ? -1 : undefined}>
        <Mic size={16} aria-hidden /> <span className="dock-cta-label">Talk to {PERSONA.display_name}</span>
      </button>
    </div>
  );
}


function DockPlaceholder({ loading = false }: { loading?: boolean }) {
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
        activity={fake.on ? fake.state : "off"}
        status={loading ? "Getting ready…" : null}
        disabled
        title="Voice is not switched on for this preview"
      />
    </>
  );
}
