/**
 * The assistant's dock, bottom right. With an agent configured it is the live
 * call (pipecat is loaded only then); without one it renders the same dock and
 * says plainly, on press, that voice is not configured in this build. Every
 * surface the assistant drives still works by hand.
 *
 * With `?debug=1` and no live client, a stand-in client is put in the Stage
 * seam so Stage attaches anyway: every performer (this site's and the banking
 * app's) is then reachable from the debug console and `window.__bankMove`.
 */
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { Suspense, lazy, useEffect, useState } from "react";
import { demo } from "../config";
import { create } from "zustand";
import { persona } from "../persona";
import { setVoiceBegin, setVoiceClient } from "../stage/client";
import { type CallState, CallTile } from "./CallTile";
import { debugMode } from "./events";
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

/** A call, faked for the `?debug=1` console: the tile and its states without a client. */
export const useFakeCall = create<{ on: boolean; state: CallState; heard: string; muted: boolean }>(() => ({
  on: false,
  state: "listening",
  heard: "",
  muted: false,
}));

/** The face before a call, and in builds without voice: the persona's initial. */
export function FaceMonogram() {
  return (
    <div className="face-placeholder" aria-hidden>
      <span>{persona.name.slice(0, 1)}</span>
    </div>
  );
}

function DockPlaceholder({ loading = false }: { loading?: boolean }) {
  const fake = useFakeCall();
  const mode = useDockMode(fake.on);
  const [said, setSaid] = useState<string | null>(null);
  const press = () => setSaid(`Voice is not configured in this build. Everything ${persona.name} would do works by hand on this page.`);
  useEffect(() => {
    setVoiceBegin(press);
    return () => setVoiceBegin(null);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!said) return;
    const t = setTimeout(() => setSaid(null), 6000);
    return () => clearTimeout(t);
  }, [said]);
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
        <FaceMonogram />
      </CallTile>
      <div className={`dock${fake.on ? " is-live is-listening" : ""}${mode.classes}`} role="region" aria-label={`Talk to ${persona.name}`}>
        <div className="dock-face dock-face-slot" aria-hidden />
        <div className="dock-text">
          <p className="dock-name">{persona.name}</p>
          <p className="dock-status" aria-live="polite">
            {fake.on ? (fake.heard ? `“${fake.heard}”` : "Listening") : loading ? "Getting ready…" : persona.role}
          </p>
        </div>
        <LangToggle live={fake.on} />
        {fake.on ? (
          <>
            <button type="button" className="dock-btn" aria-pressed={fake.muted} aria-label={fake.muted ? "Turn microphone on" : "Turn microphone off"} onClick={() => useFakeCall.setState({ muted: !fake.muted })}>
              {fake.muted ? <MicOff size={18} /> : <Mic size={18} />}
            </button>
            <button type="button" className="dock-btn dock-end" aria-label="End the call" onClick={() => useFakeCall.setState({ on: false, heard: "" })}>
              <PhoneOff size={18} />
            </button>
          </>
        ) : (
          <button type="button" className="dock-cta" onClick={press} aria-describedby={said ? "dock-note" : undefined}>
            <Mic size={16} aria-hidden /> <span className="dock-cta-label">Talk to {persona.name}</span>
          </button>
        )}
        {said ? (
          <p className="dock-note" id="dock-note" role="status">
            {said}
          </p>
        ) : null}
      </div>
    </>
  );
}
