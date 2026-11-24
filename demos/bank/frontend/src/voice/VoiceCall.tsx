/**
 * The live call — loaded only when this build carries an agent id and a
 * publishable key, so a build without voice never downloads pipecat.
 *
 * A stock `PipecatClient` over `@voqalize/client-transport` (with
 * `keepAcrossPageLoads`, so a reload mid-call rejoins it), the connect request
 * in `src/config.ts` with `init = {landing, path, lang, signed_in}`, and the
 * assistant's face from `@voqalize/avatar`, reading its state off the same
 * client; the live avatar mounts only while a call is up, and the idle dock
 * shows the character's still photo (`Face`). No transcript. Stage attaches to this client through `src/stage/client.ts` and
 * handles its own commands; the only site command is `language_changed`.
 */
import { type ComponentProps, useCallback, useEffect, useState } from "react";
import { PipecatClient, RTVIEvent, type UICommandData } from "@pipecat-ai/client-js";
import { PipecatClientProvider, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Avatar } from "@voqalize/avatar/react";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import { type VoqalizeMedia, useVoqalizeMedia } from "@voqalize/demo-kit";
import { connectRequest, withRealHeaders } from "../config";
import { landingOf, persona } from "../persona";
import { setVoiceClient } from "../stage/client";
import { currentPath } from "../stage/nav";
import { useSession } from "../state/session";
import { CallTile } from "./CallTile";
import { debugMode, setEventSender } from "./events";
import { Face } from "./Face";
import { type CallState, useFakeCall } from "./fake";
import { languageChanged, useLang } from "./lang";
import { DockBar } from "./VoiceDock";

type Activity = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

/** What the brain reads back as `session.init`: where the call started, in which language. */
function callInit() {
  const path = currentPath();
  return { landing: landingOf(path), path, lang: useLang.getState().lang, signed_in: useSession.getState().signedIn };
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
      const w = window as unknown as { __bankVoice?: Record<string, unknown> };
      w.__bankVoice = { ...w.__bankVoice, client: call.client };
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
      const response = await client.startBot({ ...connectRequest(callInit()) });
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
      setEventSender((event, payload) => call.client.sendUIEvent(event, payload));
      call.client.enableMic(true);
    }, [call.client]),
  );
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => {
      setActivity("idle");
      setMuted(false);
      setEventSender(null);
    }, []),
  );
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setActivity("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setActivity("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setActivity("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setActivity("listening"), []));

  useEffect(() => () => setEventSender(null), []);

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
        {/* Idle: the still photo; the live avatar only once the call tile is up. */}
        <Face live={live} avatar={() => <Avatar className="dock-avatar" client={call.client} character={persona.character} aria-label={persona.name} />} />
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
