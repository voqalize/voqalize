/**
 * The live call — loaded only when this build carries an agent id and a
 * publishable key, so a site without voice never downloads pipecat.
 *
 * A stock `PipecatClient` over `@voqalize/client-transport` (with
 * `keepAcrossPageLoads`, so a reload mid-call rejoins it), the connect request
 * in `src/config.ts`, and the guide's face from `@voqalize/avatar`, which reads
 * its state off the same client. Stage (src/stage/host.ts) attaches to this
 * client through the voice seam; every move and state event rides it.
 *
 * `init` says where the visitor started and the toggle's language; the brain
 * sets both speech legs from it. The page never sends voice or language config.
 */
import { type ComponentProps, useCallback, useEffect, useState } from "react";
import { PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";
import { PipecatClientProvider, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Avatar } from "@voqalize/avatar/react";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import { type VoqalizeMedia, useVoqalizeMedia } from "@voqalize/demo-kit";
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { connectRequest, withRealHeaders } from "../config";
import { persona } from "../persona";
import { setVoiceBegin, setVoiceClient } from "../stage/client";
import { appPath, useUi } from "../state/ui";
import { CallTile } from "./CallTile";
import { LanguageToggle } from "./LanguageToggle";
import { debugMode } from "./debug";
import { useDockMode } from "./useDockMode";

type Activity = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

function useCall(media: VoqalizeMedia) {
  const [call] = useState(() => {
    const transport = createVoqalizeTransport({ mediaManager: media.manager, keepAcrossPageLoads: true });
    const client = new PipecatClient({ transport, enableMic: true, enableCam: false });
    return { transport, client, bound: false, rejoining: false };
  });
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (call.bound) return;
    call.bound = true;
    media.onClient(call.client);
  }, [call, media]);
  useEffect(() => {
    if (debugMode()) {
      const w = window as unknown as { __chhatriVoice?: Record<string, unknown> };
      w.__chhatriVoice = { ...w.__chhatriVoice, client: call.client };
    }
    setVoiceClient(call.client as unknown as Parameters<typeof setVoiceClient>[0]);
    return () => setVoiceClient(null);
  }, [call]);
  useEffect(() => {
    if (call.rejoining || !call.transport.hasLiveCall) return;
    call.rejoining = true;
    call.client.connect().catch((err: unknown) => console.info("No call to rejoin:", err));
  }, [call]);
  const begin = useCallback(async () => {
    const { client, transport } = call;
    if (!["initialized", "disconnected", "error"].includes(client.state)) return;
    setError(null);
    try {
      const params = connectRequest({ surface: "insurance-web", landing: appPath(), lang: useUi.getState().lang });
      const response = await client.startBot({ ...params });
      if (typeof response === "object" && response !== null && "iceConfig" in response) {
        transport.iceServers = (response as { iceConfig: { iceServers: RTCIceServer[] } }).iceConfig.iceServers;
      }
      await client.connect(withRealHeaders(response));
    } catch (err) {
      console.error("Connection error:", err);
      setError(`${persona.name} could not connect. Check your microphone permission and try again.`);
    }
  }, [call]);
  const end = useCallback(async () => {
    try {
      await call.client.disconnectBot();
    } catch {
      /* not connected */
    }
    await call.client.disconnect();
  }, [call]);
  return { client: call.client, error, begin, end, live: call.transport.hasLiveCall };
}

export default function VoiceCall() {
  const media = useVoqalizeMedia();
  const call = useCall(media);
  return (
    <PipecatClientProvider client={call.client as unknown as ComponentProps<typeof PipecatClientProvider>["client"]}>
      <Dock call={call} />
    </PipecatClientProvider>
  );
}

function Dock({ call }: { call: ReturnType<typeof useCall> }) {
  const [state, setActivity] = useState<Activity>(call.live ? "connecting" : "idle");
  const activity: Activity = call.error ? "error" : state;
  const [heard, setHeard] = useState("");
  const [muted, setMuted] = useState(false);

  useRTVIClientEvent(
    RTVIEvent.BotReady,
    useCallback(() => {
      setActivity("listening");
      call.client.enableMic(true);
    }, [call.client]),
  );
  useRTVIClientEvent(RTVIEvent.Disconnected, useCallback(() => setActivity("idle"), []));
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(
    RTVIEvent.UserTranscript,
    useCallback((d: { text: string; final?: boolean }) => {
      if (d.text) setHeard(d.text);
    }, []),
  );

  const on = activity !== "idle" && activity !== "error";
  const mode = useDockMode(on);
  useEffect(() => {
    setVoiceBegin(() => {
      setActivity("connecting");
      void call.begin();
    });
    return () => setVoiceBegin(null);
  }, [call]);
  useEffect(() => {
    useUi.setState({ live: on });
  }, [on]);
  const STATUS: Record<Activity, string> = {
    idle: persona.role,
    connecting: "Connecting…",
    listening: muted ? "Microphone off" : "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
    error: "Could not connect",
  };

  return (
    <>
      <CallTile
        live={on}
        state={activity === "idle" ? "connecting" : activity}
        heard={heard}
        muted={muted}
        onMute={() => {
          setMuted(!muted);
          call.client.enableMic(muted);
        }}
        onEnd={() => void call.end()}
      >
        <Avatar className="dock-avatar" client={call.client} character={persona.character} aria-label={persona.name} />
      </CallTile>
      <div className={`dock${on ? " is-live is-calling" : ""} is-${activity}${mode.classes}`} role="region" aria-label={`Talk to ${persona.name}`}>
        <div className="dock-face dock-face-slot" aria-hidden />
        <div className="dock-text">
          <p className="dock-name">{persona.name}</p>
          <p className="dock-status" aria-live="polite">
            {call.error ?? (on && heard ? `“${heard}”` : STATUS[activity])}
          </p>
        </div>
        <LanguageToggle />
        {on ? (
          <>
            <button
              type="button"
              className="dock-btn"
              aria-pressed={muted}
              aria-label={muted ? "Turn microphone on" : "Turn microphone off"}
              onClick={() => {
                setMuted(!muted);
                call.client.enableMic(muted);
              }}
            >
              {muted ? <MicOff size={18} /> : <Mic size={18} />}
            </button>
            <button type="button" className="dock-btn dock-end" aria-label="End conversation" onClick={() => void call.end()}>
              <PhoneOff size={18} />
            </button>
          </>
        ) : (
          <button
            type="button"
            className="dock-cta"
            onClick={() => {
              setActivity("connecting");
              void call.begin();
            }}
          >
            <Mic size={16} /> <span className="dock-cta-label">Talk to {persona.name}</span>
          </button>
        )}
      </div>
    </>
  );
}
