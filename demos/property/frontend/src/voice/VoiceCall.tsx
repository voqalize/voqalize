/**
 * The live call. A stock `PipecatClient` over `@voqalize/client-transport`
 * (with `keepAcrossPageLoads`, so a refresh mid-call rejoins it), the connect
 * request in `src/config.ts`, and the guide's face from `@voqalize/avatar`
 * (character from persona.json), which reads its state off the same client.
 * Stage attaches to this client (`stage/host.ts`); the one plain ui-command,
 * `language_changed`, moves the language toggle.
 */
import { type ComponentProps, useCallback, useEffect, useMemo, useState } from "react";
import { type APIRequest, PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";
import { PipecatClientProvider, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Avatar } from "@voqalize/avatar/react";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import { type VoqalizeMedia, useVoqalizeMedia } from "@voqalize/demo-kit";
import type { StageClient } from "@voqalize/stage";
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { useLocation } from "react-router-dom";
import { connectRequest, withRealHeaders } from "../config";
import { PERSONA } from "../data/persona";
import { attachCall, useCall } from "../stage/host";
import { useStore } from "../state/store";
import { LanguageToggle } from "./VoiceDock";

type Activity = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

function onSiteCommand(command: string, payload: unknown) {
  if (command === "language_changed") {
    const tag = (payload as { language?: string } | null)?.language;
    if (tag && PERSONA.languages.some((l) => l.tag === tag)) useStore.getState().setLang(tag);
  }
}

function useLiveCall(media: VoqalizeMedia, params: () => APIRequest) {
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
  // Stage rides this same client for the whole call (its words segmented in the call's language).
  const lang = useStore((s) => s.lang);
  useEffect(() => {
    const client = call.client as unknown as StageClient;
    useCall.setState({ client });
    const detach = attachCall(client, lang, onSiteCommand);
    return () => {
      detach();
      useCall.setState({ client: null });
    };
  }, [call, lang]);
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
      const response = await client.startBot({ ...params() });
      if (typeof response === "object" && response !== null && "iceConfig" in response) {
        transport.iceServers = (response as { iceConfig: { iceServers: RTCIceServer[] } }).iceConfig.iceServers;
      }
      await client.connect(withRealHeaders(response));
    } catch (err) {
      console.error("Connection error:", err);
      setError(`${PERSONA.name} could not connect. Check your microphone permission and try again.`);
    }
  }, [call, params]);
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
  const location = useLocation();
  const media = useVoqalizeMedia();
  // Read at the moment the call starts: the page and language chosen then.
  const params = useMemo(
    () => () => connectRequest({ surface: "kosha-web", page: location.pathname, lang: useStore.getState().lang }),
    [location.pathname],
  );
  const call = useLiveCall(media, params);
  return (
    <PipecatClientProvider client={call.client as unknown as ComponentProps<typeof PipecatClientProvider>["client"]}>
      <Dock call={call} />
    </PipecatClientProvider>
  );
}

function Dock({ call }: { call: ReturnType<typeof useLiveCall> }) {
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
    useCallback((d: { text: string }) => {
      if (d.text) setHeard(d.text);
    }, []),
  );

  const on = activity !== "idle" && activity !== "error";
  useEffect(() => {
    useCall.setState({
      live: on,
      begin: () => {
        setActivity("connecting");
        void call.begin();
      },
    });
  }, [on, call]);
  const STATUS: Record<Activity, string> = {
    idle: PERSONA.role,
    connecting: "Connecting…",
    listening: muted ? "Microphone off" : "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
    error: "Could not connect",
  };

  return (
    <div className={`dock${on ? " is-live" : ""} is-${activity}`} role="region" aria-label={`Talk to ${PERSONA.name}`}>
      <div className="dock-face">
        <Avatar className="dock-avatar" client={call.client} character={PERSONA.character} aria-label={PERSONA.name} />
      </div>
      <div className="dock-text">
        <p className="dock-name">{PERSONA.name}</p>
        <p className="dock-status" aria-live="polite">
          {call.error ?? (on && heard ? `“${heard}”` : STATUS[activity])}
        </p>
      </div>
      <LanguageToggle disabled={on} />
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
          <Mic size={16} /> <span>Talk to {PERSONA.name}</span>
        </button>
      )}
    </div>
  );
}
