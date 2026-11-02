import { Mic } from "lucide-react";
import { Suspense, lazy } from "react";
import { demo } from "../config";
import { create } from "zustand";
import { type CallState, CallTile } from "./CallTile";
import { useDockMode } from "./useDockMode";

const VoiceCall = lazy(() => import("./VoiceCall"));

/** True when this build carries the wiring for a call. */
export const voiceReady = () => !!demo.agentId && !!demo.publishableKey;

/**
 * Emily's dock, bottom centre. With an agent configured it is the live call;
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

/**
 * A call, faked for the `?debug=1` console: the tile and its states without
 * a client, so the connected look can be seen and screenshotted.
 */
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
        <div className="face-placeholder" aria-hidden>
          <span>E</span>
        </div>
      </CallTile>
      <div className={`dock is-off${fake.on ? " is-calling" : ""}${mode.classes}`} role="region" aria-label="Talk to Emily">
        <div className="dock-face dock-face-slot" aria-hidden />
        <div className="dock-text">
          <p className="dock-name">Emily</p>
          <p className="dock-status">{loading ? "Getting ready…" : "Voice coming soon"}</p>
        </div>
        <button type="button" className="dock-cta" disabled title="Voice is not switched on for this preview">
          <Mic size={16} /> <span className="dock-cta-label">Talk to Emily</span>
        </button>
      </div>
    </>
  );
}
