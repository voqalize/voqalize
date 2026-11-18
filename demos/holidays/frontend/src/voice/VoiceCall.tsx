/**
 * The live call — loaded only when this build carries an agent id and a
 * publishable key, so a site without voice never downloads pipecat.
 *
 * A stock `PipecatClient` over `@voqalize/client-transport` (rejoins across a
 * reload), the connect request from `config.ts`, and the planner's face from
 * `@voqalize/avatar` with the character persona.json names. Stage attaches to
 * this client (`stage/host.tsx`); every screen change arrives as a Stage move.
 * Before the microphone opens, the gallery's consent gate.
 */
import { type ComponentProps, useCallback, useEffect, useState } from "react";
import { type APIRequest, PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";
import { PipecatClientProvider, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Avatar } from "@voqalize/avatar/react";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import { DemoGate, type VoqalizeMedia, useVoqalizeMedia } from "@voqalize/demo-kit";
import { connectRequest, withRealHeaders } from "../config";
import { PERSONA } from "../persona";
import { setVoiceBegin, setVoiceClient, setVoiceLive } from "../stage/client";
import { currentPath } from "../stage/nav";
import { tripForInit } from "../state/trip";
import { type CallState, Dock } from "./Dock";
import { LangToggle } from "./LangToggle";
import { useLang } from "./lang";

/** What the brain starts from (CONTRACT, Pages): the landing, the language, and a trip built by hand. */
function initPayload(): Record<string, unknown> {
  const p = currentPath();
  const trip = tripForInit();
  return { page: p === "/" ? "home" : "plan", lang: useLang.getState().lang, ...(trip ? { trip } : {}) };
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
      throw err;
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
      <Live call={call} />
    </PipecatClientProvider>
  );
}

function Live({ call }: { call: ReturnType<typeof useCall> }) {
  const [state, setState] = useState<CallState>(call.live ? "connecting" : "idle");
  const [heard, setHeard] = useState("");
  const [muted, setMuted] = useState(false);
  const [gate, setGate] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const activity: CallState = call.error ? "error" : state;

  useRTVIClientEvent(
    RTVIEvent.BotReady,
    useCallback(() => {
      setState("listening");
      call.client.enableMic(true);
      useLang.setState({ sender: (language) => call.client.sendUIEvent("language_chosen", { language }) });
    }, [call.client]),
  );
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => {
      setState("idle");
      setHeard("");
      useLang.setState({ sender: null });
    }, []),
  );
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setState("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setState("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setState("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setState("listening"), []));
  useRTVIClientEvent(
    RTVIEvent.UserTranscript,
    useCallback((d: { text: string }) => {
      if (d.text) setHeard(d.text);
    }, []),
  );

  const on = activity !== "idle" && activity !== "error";
  useEffect(() => setVoiceLive(on), [on]);
  useEffect(() => {
    setVoiceBegin(() => setGate(true));
    return () => setVoiceBegin(null);
  }, []);

  return (
    <>
      <DemoGate
        open={gate}
        title={`Talk to ${PERSONA.name}`}
        blurb={`Tell ${PERSONA.name} where you'd like to go, when and who's travelling. She builds the flights, stays and days on this page while you talk, and you can change anything by voice or by hand.`}
        agreed={agreed}
        onAgreedChange={setAgreed}
        busy={activity === "connecting"}
        error={call.error}
        accent="#e8913a"
        theme="light"
        dismissible
        onDismiss={() => setGate(false)}
        joinLabel={`Start talking to ${PERSONA.name}`}
        onJoin={async () => {
          setState("connecting");
          try {
            await call.begin();
            setGate(false);
          } catch {
            setState("error");
          }
        }}
      >
        <div className="gate-lang">
          <span>Speak in</span>
          <LangToggle />
        </div>
      </DemoGate>
      <Dock
        state={activity}
        heard={heard}
        muted={muted}
        face={<Avatar className="dock-avatar" client={call.client as never} character={PERSONA.character} aria-label={PERSONA.name} />}
        onStart={() => setGate(true)}
        onMute={() => {
          call.client.enableMic(muted);
          setMuted(!muted);
        }}
        onEnd={() => void call.end()}
      />
    </>
  );
}
