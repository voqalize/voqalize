/**
 * The live call, loaded only when this build carries an agent id and a
 * publishable key. A stock `PipecatClient` over `@voqalize/client-transport`
 * (with `keepAcrossPageLoads`, so a refresh mid-call rejoins it), the connect
 * request in `src/config.ts`, and the guide's face from `@voqalize/avatar`
 * (character from persona.json), which reads its state off the same client;
 * it mounts only while a call is up, and the idle dock shows the character's
 * still photo (`Face`). Stage attaches to this client (`stage/host.ts`); the
 * one plain ui-command, `language_changed`, moves the language toggle.
 */
import { type ComponentProps, useCallback, useEffect, useState } from "react";
import { PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";
import { PipecatClientProvider, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Avatar } from "@voqalize/avatar/react";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import { type VoqalizeMedia, useVoqalizeMedia } from "@voqalize/demo-kit";
import type { StageClient } from "@voqalize/stage";
import { connectRequest, withRealHeaders } from "../config";
import { PERSONA } from "../data/persona";
import { attachCall, useCall } from "../stage/host";
import { useStore } from "../state/store";
import { CallTile } from "./CallTile";
import { type CallState, useFakeCall } from "./fake";
import { Face } from "./Face";
import { languageChanged, useLangLink } from "./lang";
import { DockBar } from "./VoiceDock";

type Activity = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

function onSiteCommand(command: string, payload: unknown) {
  if (command === "language_changed") languageChanged(payload);
}

/** The route under the app's base, as the brain reads `init.page`. */
const currentPage = () => {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  const path = window.location.pathname;
  const route = (path.startsWith(base) ? path.slice(base.length) : path) || "/";
  // A product page's URL carries its id in the query (/p/?id=7421).
  return /^\/p\/?$/.test(route) ? `${route}${window.location.search}` : route;
};

function useLiveCall(media: VoqalizeMedia) {
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
      // Read at the moment the call starts: the page and the language chosen then.
      const params = connectRequest({ surface: "fashio-web", page: currentPage(), lang: useStore.getState().lang });
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
  const call = useLiveCall(media);
  return (
    <PipecatClientProvider client={call.client as unknown as ComponentProps<typeof PipecatClientProvider>["client"]}>
      <Dock call={call} />
    </PipecatClientProvider>
  );
}

function Dock({ call }: { call: ReturnType<typeof useLiveCall> }) {
  const [state, setActivity] = useState<Activity>(call.live ? "connecting" : "idle");
  const activity: Activity = call.error ? "error" : state;
  const [muted, setMuted] = useState(false);
  const fake = useFakeCall();

  useRTVIClientEvent(
    RTVIEvent.BotReady,
    useCallback(() => {
      setActivity("listening");
      useLangLink.setState({ send: (event, payload) => call.client.sendUIEvent(event, payload) });
      call.client.enableMic(true);
    }, [call.client]),
  );
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => {
      setActivity("idle");
      setMuted(false);
      useLangLink.setState({ send: null });
    }, []),
  );
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity("listening"), []));
  useEffect(() => () => useLangLink.setState({ send: null }), []);

  const on = activity !== "idle" && activity !== "error";
  const talk = useCallback(() => {
    setActivity("connecting");
    void call.begin();
  }, [call]);
  useEffect(() => {
    useCall.setState({ live: on, begin: talk });
  }, [on, talk]);
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
        {/* Idle: the still photo; the live avatar only once the call tile is up. */}
        <Face live={live} avatar={() => <Avatar className="dock-avatar" client={call.client} character={PERSONA.character} aria-label={PERSONA.name} />} />
      </CallTile>
      <DockBar calling={live} activity={activity} status={call.error} onTalk={talk} />
    </>
  );
}
