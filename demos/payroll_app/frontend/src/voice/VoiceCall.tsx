/**
 * The live call, loaded only when this build carries an agent id and a
 * publishable key. A stock client over `@voqalize/client-transport`, the
 * connect request from `src/config.ts`, and the guide's face from
 * `@voqalize/avatar` (the character named in persona.json), which reads its
 * state off the same client. Stage attaches to this client (`stage/runtime`):
 * cues and tool moves run through the one `Moves` the app made at start.
 */
import { type ComponentProps, useCallback, useEffect, useState } from "react";
import { PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";
import { PipecatClientProvider, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Avatar } from "@voqalize/avatar/react";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import { type VoqalizeMedia, useVoqalizeMedia } from "@voqalize/demo-kit";
import type { StageClient } from "@voqalize/stage";
import { connectRequest, withRealHeaders } from "../config";
import { PERSONA } from "../persona";
import { currentPath } from "../state/nav";
import { attach, hello } from "../stage/runtime";
import { languageChanged, useLang } from "./lang";
import { debugMode } from "./debug";
import { CallTile } from "./CallTile";
import { type CallState, useFakeCall } from "./fake";
import { DockBar } from "./VoiceDock";

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
  // Stage on this client, for as long as the dock lives.
  useEffect(() => {
    if (debugMode()) (window as unknown as { __tkClient?: unknown }).__tkClient = call.client;
    return attach(call.client as unknown as StageClient, (command, payload) => {
      if (command === "language_changed") languageChanged(payload);
    });
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
      // The landing picks the guide's job: /welcome onboarding, / and /help support, else coach.
      const landing = currentPath().split("?")[0] || "/";
      const params = connectRequest({ surface: "payroll_app", landing, lang: useLang.getState().lang });
      const response = await client.startBot({ ...params });
      if (typeof response === "object" && response !== null && "iceConfig" in response) {
        transport.iceServers = (response as { iceConfig: { iceServers: RTCIceServer[] } }).iceConfig.iceServers;
      }
      await client.connect(withRealHeaders(response));
    } catch (err) {
      console.error("Connection error:", err);
      setError(`${PERSONA.display_name} could not connect. Check your microphone permission and try again.`);
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
  const [muted, setMuted] = useState(false);
  const fake = useFakeCall();

  useRTVIClientEvent(
    RTVIEvent.BotReady,
    useCallback(() => {
      setActivity("listening");
      useLang.setState({ send: (event, payload) => call.client.sendUIEvent(event, payload) });
      call.client.enableMic(true);
      hello();
    }, [call.client]),
  );
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => {
      setActivity("idle");
      setMuted(false);
      useLang.setState({ send: null });
    }, []),
  );
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity("listening"), []));
  useEffect(() => () => useLang.setState({ send: null }), []);

  const on = activity !== "idle" && activity !== "error";
  // `?debug=1` can fake a call over the real dock, to see and screenshot the tile.
  const live = on || fake.on;
  const toggleMute = () => {
    if (fake.on && !on) {
      useFakeCall.setState({ muted: !fake.muted });
      return;
    }
    call.client.enableMic(muted);
    setMuted(!muted);
  };
  return (
    <>
      <CallTile
        live={live}
        state={on ? (activity as CallState) : fake.on ? fake.state : "connecting"}
        muted={on ? muted : fake.muted}
        onMute={toggleMute}
        onEnd={() => (on ? void call.end() : useFakeCall.setState({ on: false }))}
      >
        <Avatar className="dock-avatar" client={call.client} character={PERSONA.avatar_character} aria-label={PERSONA.display_name} />
      </CallTile>
      <DockBar
        calling={live}
        activity={activity}
        status={call.error}
        onTalk={() => {
          setActivity("connecting");
          void call.begin();
        }}
      />
    </>
  );
}
