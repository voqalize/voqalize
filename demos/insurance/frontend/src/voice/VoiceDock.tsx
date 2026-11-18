import { Mic, MicOff, PhoneOff } from "lucide-react";
import { Suspense, lazy } from "react";
import { create } from "zustand";
import { Portrait } from "../components/bits";
import { demo } from "../config";
import { persona } from "../persona";
import { type CallState, CallTile } from "./CallTile";
import { LanguageToggle } from "./LanguageToggle";
import { useDockMode } from "./useDockMode";

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

/**
 * The guide's dock, bottom centre. With an agent configured it is the live
 * call; without one it says so plainly, and everything the agent would drive
 * still works by hand.
 */
export function VoiceDock() {
  if (!voiceReady()) return <DockPlaceholder />;
  return (
    <Suspense fallback={<DockPlaceholder loading />}>
      <VoiceCall />
    </Suspense>
  );
}

/** A call, faked for the `?debug=1` console: the tile and its states without a client. */
export const useFakeCall = create<{ on: boolean; state: CallState; heard: string; muted: boolean }>(() => ({
  on: false,
  state: "listening",
  heard: "",
  muted: false,
}));

function DockPlaceholder({ loading = false }: { loading?: boolean }) {
  const fake = useFakeCall();
  const mode = useDockMode(fake.on);
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
        <Portrait className="face-portrait" />
      </CallTile>
      <div className={`dock is-off${fake.on ? " is-calling is-live" : ""}${mode.classes}`} role="region" aria-label={`Talk to ${persona.name}`}>
        <div className="dock-face dock-face-slot" aria-hidden />
        <div className="dock-text">
          <p className="dock-name">{persona.name}</p>
          <p className="dock-status">{fake.on ? (fake.heard ? `“${fake.heard}”` : "Listening") : loading ? "Getting ready…" : "Voice coming soon"}</p>
        </div>
        <LanguageToggle />
        {fake.on ? (
          <>
            <button type="button" className="dock-btn" aria-pressed={fake.muted} aria-label="Turn microphone off" onClick={() => useFakeCall.setState({ muted: !fake.muted })}>
              {fake.muted ? <MicOff size={18} /> : <Mic size={18} />}
            </button>
            <button type="button" className="dock-btn dock-end" aria-label="End conversation" onClick={() => useFakeCall.setState({ on: false, heard: "" })}>
              <PhoneOff size={18} />
            </button>
          </>
        ) : (
          <button type="button" className="dock-cta" disabled title="Voice is not switched on for this preview">
            <Mic size={16} /> <span className="dock-cta-label">Talk to {persona.name}</span>
          </button>
        )}
      </div>
    </>
  );
}
