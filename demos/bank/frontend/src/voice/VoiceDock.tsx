/**
 * The assistant's one entry point (Paynora's widget). Idle, a pill at the
 * bottom right: the still face, the name, the job on this page (persona.json
 * `roles`), the EN / हिंदी toggle and "Talk to {name}". In a call the pill goes
 * away and the face becomes the floating call tile (`CallTile`), which holds
 * the language toggle, mute, minimise and end. No transcript is shown anywhere.
 *
 * With an agent configured the call is live (pipecat is loaded only then);
 * without one the pill says so and every surface works by hand. With
 * `?debug=1` and no live client, a stand-in client is put in the Stage seam so
 * Stage attaches anyway (every performer reachable from the debug console and
 * `window.__bankMove`), and the console can fake a call to show the tile.
 */
import { Mic } from "lucide-react";
import { Suspense, lazy, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { demo } from "../config";
import { persona, roleFor } from "../persona";
import { setVoiceClient } from "../stage/client";
import { CallTile } from "./CallTile";
import { debugMode } from "./events";
import { Face } from "./Face";
import { useFakeCall } from "./fake";
import { LangToggle } from "./LangToggle";
import { useDockMode } from "./useDockMode";

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

export function VoiceDock() {
  useEffect(() => {
    if (voiceReady() || !debugMode()) return;
    // Stage needs a client to attach to; this one sends nowhere.
    setVoiceClient({ on() {}, off() {}, sendUIEvent() {} });
    return () => setVoiceClient(null);
  }, []);
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
    <div
      className={`dock is-${activity}${calling ? " is-calling" : ""}${mode.classes}`}
      role="region"
      aria-label={`Talk to ${persona.name}`}
      aria-hidden={calling || undefined}
    >
      <div className="dock-face dock-face-slot" aria-hidden />
      <div className="dock-text">
        <p className="dock-name">{persona.name}</p>
        <p className="dock-status" aria-live="polite" title={status ?? role}>
          {status ?? role}
        </p>
      </div>
      <LangToggle />
      <button
        type="button"
        className="dock-cta"
        aria-label={`Talk to ${persona.name}`}
        disabled={disabled}
        title={title}
        onClick={onTalk}
        tabIndex={calling ? -1 : undefined}
      >
        <Mic size={16} aria-hidden /> <span className="dock-cta-label">
          Talk<span className="dock-cta-name"> to {persona.name}</span>
        </span>
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
