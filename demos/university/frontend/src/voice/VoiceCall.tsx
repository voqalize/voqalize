/**
 * The live call, loaded only when this build carries an agent id and a
 * publishable key, so a page without voice never downloads pipecat.
 *
 * A stock `PipecatClient` over `@voqalize/client-transport` (with
 * `keepAcrossPageLoads`, so a reload mid-call rejoins it), the connect request
 * in `src/config.ts`, and the persona's face from `@voqalize/avatar`, which
 * reads its state off the same client. Stage attaches to this client
 * (`attachCall`); its own ui-commands go to the app-wide `Moves`, and
 * everything else (`language_changed`) comes back here as a site command.
 */
import { type ComponentProps, useCallback, useEffect, useState } from "react";
import { PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";
import { PipecatClientProvider, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Avatar } from "@voqalize/avatar/react";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import type { StageClient } from "@voqalize/stage";
import { type VoqalizeMedia, useVoqalizeMedia } from "@voqalize/demo-kit";
import { connectRequest, withRealHeaders } from "../config";
import { PERSONA, isLang } from "../data/persona";
import { announce, attachCall, currentPath, useCall } from "../stage/host";
import { sendSnapshot } from "../stage/report";
import { type Activity, Dock } from "./Dock";
import { useLanguage } from "./language";

function useClient(media: VoqalizeMedia) {
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
    if (call.rejoining || !call.transport.hasLiveCall) return;
    call.rejoining = true;
    call.client.connect().catch((err: unknown) => console.info("No call to rejoin:", err));
  }, [call]);
  const begin = useCallback(async () => {
    const { client, transport } = call;
    if (!["initialized", "disconnected", "error"].includes(client.state)) return;
    setError(null);
    // Read where the visitor is at the moment the call starts.
    const init = { surface: "university-web", landing: currentPath(), lang: useLanguage.getState().lang };
    try {
      const response = await client.startBot(connectRequest(init));
      if (typeof response === "object" && response !== null && "iceConfig" in response) {
        transport.iceServers = (response as { iceConfig: { iceServers: RTCIceServer[] } }).iceConfig.iceServers;
      }
      await client.connect(withRealHeaders(response));
    } catch (err) {
      console.error("Connection error:", err);
      setError(`${PERSONA.name} could not connect. Check your microphone permission and try again.`);
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
  const call = useClient(media);
  return (
    <PipecatClientProvider client={call.client as unknown as ComponentProps<typeof PipecatClientProvider>["client"]}>
      <LiveDock call={call} />
    </PipecatClientProvider>
  );
}

function LiveDock({ call }: { call: ReturnType<typeof useClient> }) {
  const [state, setActivity] = useState<Activity>(call.live ? "connecting" : "idle");
  const activity: Activity = call.error ? "error" : state;
  const [heard, setHeard] = useState("");
  const [muted, setMuted] = useState(false);
  const lang = useLanguage((s) => s.lang);

  // Stage on this client, for as long as the dock lives; again when the language moves.
  useEffect(() => {
    const client = call.client as unknown as StageClient;
    const detach = attachCall(client, lang, (command, payload) => {
      if (command !== "language_changed") return;
      const next = (payload as { language?: unknown } | null)?.language;
      if (isLang(next)) useLanguage.getState().follow(next);
    });
    return detach;
  }, [call.client, lang]);

  // The toggle, pressed mid-call, asks the brain to switch.
  useEffect(() => {
    useLanguage.setState({
      request: (language) => {
        if (call.client.state !== "ready") return;
        try {
          call.client.sendUIEvent("language_requested", { language });
        } catch (err) {
          console.warn("language_requested not sent:", err);
        }
      },
    });
    return () => useLanguage.setState({ request: null });
  }, [call.client]);

  useRTVIClientEvent(
    RTVIEvent.BotReady,
    useCallback(() => {
      setActivity("listening");
      useCall.setState({ live: true });
      call.client.enableMic(true);
      announce();
      sendSnapshot(currentPath());
    }, [call.client]),
  );
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => {
      setActivity("idle");
      setHeard("");
      useCall.setState({ live: false });
    }, []),
  );
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

  useEffect(() => {
    useCall.setState({ client: call.client as unknown as StageClient });
    return () => useCall.setState({ client: null, live: false });
  }, [call.client]);

  const STATUS: Record<Activity, string> = {
    idle: PERSONA.role,
    connecting: "Connecting…",
    listening: muted ? "Microphone off" : "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
    error: "Could not connect",
  };

  return (
    <Dock
      face={<Avatar className="dock-avatar" client={call.client} character={PERSONA.character} aria-label={PERSONA.name} />}
      activity={activity}
      status={call.error ?? (activity === "listening" && heard ? `“${heard}”` : STATUS[activity])}
      muted={muted}
      onCall={() => {
        setActivity("connecting");
        void call.begin();
      }}
      onMute={() => {
        call.client.enableMic(muted);
        setMuted(!muted);
      }}
      onEnd={() => void call.end()}
    />
  );
}
