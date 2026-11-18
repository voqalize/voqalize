/**
 * The live call — loaded only when this build carries an agent id and a
 * publishable key, so a page without voice never downloads pipecat.
 *
 * A stock `PipecatClient` over `@voqalize/client-transport` (with
 * `keepAcrossPageLoads`, so a reload mid-call rejoins it), the connect request
 * in `src/config.ts`, and the front desk's face from `@voqalize/avatar`, which
 * reads its state off the same client. The page sends only `init`: voice and
 * language belong to the brain. Stage attaches to this same client
 * (`stage/host.ts`); the one plain ui-command is `language_changed`.
 */
import { type ComponentProps, useCallback, useEffect, useState } from "react";
import { PipecatClient, RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import { PipecatClientProvider, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Avatar } from "@voqalize/avatar/react";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import { type VoqalizeMedia, useVoqalizeMedia } from "@voqalize/demo-kit";
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { connectRequest, withRealHeaders } from "../config";
import { displayName, persona } from "../persona";
import { setVoiceBegin, setVoiceClient, setVoiceLive } from "../stage/client";
import { currentPage, currentPath } from "../stage/nav";
import { actions, sendSchedule, signedInPatient, useStore } from "../state/store";
import { LangToggle } from "../components/LangToggle";
import { asUiAction } from "./events.gen";
import { debugMode, emit, setEventSender } from "./events";
import { CallTile } from "./CallTile";
import { callLabel } from "./label";
import { useDockMode } from "./useDockMode";

type Activity = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

/** `init`: where the call starts and in which language. Nothing else. */
function initNow() {
  return { surface: "dental-web", landing: currentPage(), path: currentPath(), lang: useStore.getState().lang };
}

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
      const w = window as unknown as { __dentalVoice?: Record<string, unknown> };
      w.__dentalVoice = { ...w.__dentalVoice, client: call.client };
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
      const response = await client.startBot({ ...connectRequest(initNow()) });
      if (typeof response === "object" && response !== null && "iceConfig" in response) {
        transport.iceServers = (response as { iceConfig: { iceServers: RTCIceServer[] } }).iceConfig.iceServers;
      }
      await client.connect(withRealHeaders(response));
    } catch (err) {
      console.error("Connection error:", err);
      setError(`${displayName} could not connect. Check your microphone permission and try again.`);
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
  const lang = useStore((s) => s.lang);

  useRTVIClientEvent(
    RTVIEvent.UICommand,
    useCallback(({ command, payload }: UICommandData) => {
      // Stage's own commands are Stage's; this page's one plain action:
      const action = asUiAction(command, payload);
      if (action?.command === "language_changed") actions.setLang(action.payload.language);
    }, []),
  );
  useRTVIClientEvent(
    RTVIEvent.BotReady,
    useCallback(() => {
      setActivity("listening");
      setEventSender((event, payload) => call.client.sendUIEvent(event, payload));
      call.client.enableMic(true);
      // Where the visitor is, who they are, and what this browser changed.
      emit("page_viewed", { page: currentPage(), path: currentPath() });
      const p = signedInPatient();
      if (p) emit("patient_signed_in", { patient_id: p.id, name: p.name, phone: p.phone, is_new: false });
      sendSchedule();
    }, [call.client]),
  );
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => {
      setActivity("idle");
      setEventSender(null);
      useStore.setState({ pendingLang: null });
    }, []),
  );
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

  useEffect(() => () => setEventSender(null), []);

  const on = activity !== "idle" && activity !== "error";
  const mode = useDockMode(on);
  useEffect(() => {
    setVoiceBegin(() => {
      setActivity("connecting");
      void call.begin();
    });
    return () => setVoiceBegin(null);
  }, [call]);
  useEffect(() => setVoiceLive(on), [on]);
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
        <span className="face-initial" aria-hidden>
          {displayName.slice(0, 1)}
        </span>
        <Avatar className="dock-avatar" client={call.client} character={persona.character} aria-label={displayName} />
      </CallTile>
      <div className={`dock${on ? " is-live is-calling" : ""} is-${activity}${mode.classes}`} role="region" aria-label={callLabel(lang)}>
        <div className="dock-face dock-face-slot" aria-hidden />
        <div className="dock-text">
          <p className="dock-name">{displayName}</p>
          <p className="dock-status" aria-live="polite">
            {call.error ?? (on && heard ? `“${heard}”` : STATUS[activity])}
          </p>
        </div>
        <LangToggle compact />
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
            <Mic size={16} /> <span className="dock-cta-label">{callLabel(lang)}</span>
          </button>
        )}
      </div>
    </>
  );
}
