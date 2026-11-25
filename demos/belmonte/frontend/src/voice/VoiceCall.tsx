/**
 * The live call — loaded only when this build carries an agent id and a
 * publishable key, so a site without voice never downloads pipecat.
 *
 * A stock `PipecatClient` over `@voqalize/client-transport` (rejoins across a
 * reload), the connect request from `config.ts`, and the concierge's face from
 * `@voqalize/avatar` with the character persona.json names; the live avatar
 * mounts only while a call is up, and the idle bar shows her still photo
 * (`Face`). No transcript. Stage attaches to this client (`stage/host.tsx`);
 * every screen change arrives as a Stage move, and the one site command is
 * `language_changed`.
 */
import { type ComponentProps, useCallback, useEffect, useState } from "react";
import { type APIRequest, PipecatClient, RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import { PipecatClientProvider, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Avatar } from "@voqalize/avatar/react";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import { type VoqalizeMedia, useVoqalizeMedia } from "@voqalize/demo-kit";
import { connectRequest, withRealHeaders } from "../config";
import { PERSONA } from "../persona";
import { setVoiceClient } from "../stage/client";
import { currentPath, pageOfPath } from "../stage/nav";
import { stayForInit } from "../state/store";
import { debugMode } from "./debug";
import { Face } from "./Face";
import { type CallState, useFakeCall } from "./fake";
import { languageChanged, useLang } from "./lang";
import { Widget } from "./Widget";

type Activity = "idle" | CallState;

/** What the brain starts from (CONTRACT.md, "The call"): the screen, the language, and the stay as the app has it. */
function initPayload(): Record<string, unknown> {
  return { page: pageOfPath(currentPath()), lang: useLang.getState().lang, stay: stayForInit() };
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
      const w = window as unknown as { __bmVoice?: Record<string, unknown> };
      w.__bmVoice = { ...w.__bmVoice, client: call.client };
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
      const params: APIRequest = connectRequest(initPayload());
      const response = await client.startBot({ ...params });
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
    RTVIEvent.UICommand,
    useCallback(({ command, payload }: UICommandData) => {
      // Stage's own commands reach Stage through the client; this is the site's one.
      if (command === "language_changed") languageChanged(payload);
    }, []),
  );
  useRTVIClientEvent(
    RTVIEvent.BotReady,
    useCallback(() => {
      setActivity("listening");
      call.client.enableMic(true);
      useLang.setState({ sender: (language) => void call.client.sendUIEvent("language_chosen", { language }) });
    }, [call.client]),
  );
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => {
      setActivity("idle");
      setMuted(false);
      useLang.setState({ sender: null });
    }, []),
  );
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity("listening"), []));

  useEffect(() => () => useLang.setState({ sender: null }), []);

  const on = activity !== "idle" && activity !== "error";
  // `?debug=1` can fake a call to see and screenshot the in-call widget.
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
    <Widget
      live={live}
      state={on ? (activity as CallState) : fake.on ? fake.state : "connecting"}
      muted={on ? muted : fake.muted}
      onMute={toggleMute}
      onEnd={() => (on ? void call.end() : useFakeCall.setState({ on: false }))}
      status={call.error}
      onTalk={() => {
        setActivity("connecting");
        void call.begin();
      }}
    >
      {/* Idle (and a faked call): the still photo; the live avatar only once a real call is up. */}
      <Face live={on} avatar={() => <Avatar className="dock-avatar" client={call.client as never} character={PERSONA.character} aria-label={PERSONA.name} />} />
    </Widget>
  );
}
