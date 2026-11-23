/**
 * The live call — loaded only when this build carries an agent id and a
 * publishable key.
 *
 * A stock `PipecatClient` over `@voqalize/client-transport` (the media is
 * ours: `useVoqalizeMedia`), the connect request in `src/config.ts` with
 * `init: {page, lang}` (the landing page picks the agent's job, the toggle its
 * language), and the face from `@voqalize/avatar` with the character in
 * persona.json. Stage attaches to the same client (`stage/host.tsx`); the
 * language toggle mid-call sends `language_requested`, and the brain's
 * `language_changed` moves the toggle back. The dock pill carries the toggle
 * before the call and the face tile during it; neither shows what the visitor
 * said.
 */
import { type ComponentProps, useCallback, useEffect, useMemo, useState } from "react";
import { PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";
import { PipecatClientProvider, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { Avatar } from "@voqalize/avatar/react";
import { createVoqalizeTransport } from "@voqalize/client-transport";
import type { StageClient } from "@voqalize/stage";
import { useVoqalizeMedia } from "@voqalize/demo-kit";
import { connectRequest, withRealHeaders } from "../config";
import { PERSONA } from "../persona";
import { actions, useSite } from "../state/store";
import { attachCall, currentPath, sendSiteEvent, useCall } from "../stage/host";
import { type CallState, DockView } from "./DockView";
import { endFakeCall, useFakeCall } from "./fakeCall";

export default function VoiceCall() {
  const media = useVoqalizeMedia();
  const [call] = useState(() => {
    const transport = createVoqalizeTransport({ mediaManager: media.manager });
    const client = new PipecatClient({ transport, enableMic: true, enableCam: false });
    return { transport, client };
  });
  useEffect(() => {
    media.onClient(call.client);
  }, [call, media]);
  return (
    <PipecatClientProvider client={call.client as unknown as ComponentProps<typeof PipecatClientProvider>["client"]}>
      <Live client={call.client} transport={call.transport} />
    </PipecatClientProvider>
  );
}

function Live({ client, transport }: { client: PipecatClient; transport: ReturnType<typeof createVoqalizeTransport> }) {
  const [state, setState] = useState<CallState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const lang = useSite((s) => s.lang);
  const live = state !== "idle" && state !== "error";

  // Stage rides this client from the moment the bot is ready until it goes.
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!ready) return;
    useCall.setState({ client: client as unknown as StageClient, live: true });
    const detach = attachCall(client as unknown as StageClient, useSite.getState().lang, (command, payload) => {
      if (command === "language_changed") actions.setLang(String((payload as { language?: string })?.language ?? PERSONA.default_language));
    });
    return () => {
      detach();
      useCall.setState({ client: null, live: false });
    };
  }, [ready, client]);

  const begin = useCallback(async () => {
    if (!["initialized", "disconnected", "error"].includes(client.state)) return;
    setError(null);
    setState("connecting");
    try {
      const params = connectRequest({ page: currentPath(), lang: useSite.getState().lang, surface: "payroll-site-web" });
      const response = await client.startBot({ ...params });
      if (typeof response === "object" && response !== null && "iceConfig" in response) {
        transport.iceServers = (response as { iceConfig: { iceServers: RTCIceServer[] } }).iceConfig.iceServers;
      }
      await client.connect(withRealHeaders(response));
    } catch (err) {
      console.error("Connection error:", err);
      setState("error");
      setError(`${PERSONA.display_name} could not connect. Check your microphone permission and try again.`);
    }
  }, [client, transport]);
  useEffect(() => {
    useCall.setState({ begin: () => void begin() });
    return () => useCall.setState({ begin: null });
  }, [begin]);

  const end = useCallback(async () => {
    try {
      await client.disconnectBot();
    } catch {
      /* not connected */
    }
    await client.disconnect();
  }, [client]);

  useRTVIClientEvent(
    RTVIEvent.BotReady,
    useCallback(() => {
      setState("listening");
      setReady(true);
      client.enableMic(true);
    }, [client]),
  );
  useRTVIClientEvent(
    RTVIEvent.Disconnected,
    useCallback(() => {
      setState("idle");
      setReady(false);
      setMuted(false);
    }, []),
  );
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setState("listening"), []));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, useCallback(() => setState("thinking"), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setState("speaking"), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setState("listening"), []));

  const face = useMemo(
    () => <Avatar className="agent-avatar" client={client as never} character={PERSONA.avatar_character} aria-label={PERSONA.display_name} />,
    [client],
  );

  // `?debug=1` can fake a call for the live look; a real one always wins.
  const fake = useFakeCall();
  if (state === "idle" && fake.state !== "idle") {
    return (
      <DockView
        state={fake.state}
        muted={fake.muted}
        onStart={() => undefined}
        onMute={() => useFakeCall.setState({ muted: !fake.muted })}
        onEnd={endFakeCall}
        onLanguage={(code) => actions.setLang(code)}
        face={face}
      />
    );
  }

  return (
    <DockView
      state={state}
      muted={muted}
      error={error}
      onStart={() => void begin()}
      onMute={() => {
        setMuted(!muted);
        client.enableMic(muted);
      }}
      onEnd={() => void end()}
      onLanguage={(code) => {
        if (code === lang) return;
        actions.setLang(code);
        // Before the call the choice rides `init`; during it the brain moves both legs.
        if (live) sendSiteEvent("language_requested", { language: code });
      }}
      face={face}
    />
  );
}
