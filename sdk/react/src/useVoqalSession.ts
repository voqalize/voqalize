/**
 * useVoqalSession — the full lifecycle of one Voqalize voice session in a hook.
 *
 * Encapsulates: mint a session ({@link createSession}) → build a
 * {@link VoqalWebRTCTransport} → drive a `PipecatClient` → surface connection
 * state, a coarse bot state, mic control, and normalized server messages.
 *
 * Modelled on the console Playground's `usePipecatSession`. Keep it thin: it owns
 * a single `PipecatClient` at a time and tears it down on unmount.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { PipecatClient } from "@pipecat-ai/client-js";
import { VoqalWebRTCTransport } from "./transport";
import {
  createSession,
  type VoqalPipelineConfig,
} from "./createSession";

/** Transport-level connection lifecycle. */
export type VoqalConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

/** Coarse conversational state of the agent, derived from RTVI events. */
export type VoqalBotState = "idle" | "listening" | "thinking" | "speaking";

const DEFAULT_ICE_SERVERS: RTCIceServer[] = [
  { urls: "stun:stun.l.google.com:19302" },
];

/** Options for {@link useVoqalSession}. */
export interface UseVoqalSessionOptions {
  /** Versioned API root, e.g. `"/api/v1"`. */
  apiBase: string;
  /** Tenant slug. */
  tenantSlug: string;
  /** Publishable (`pk_...`) key. */
  publishableKey: string;
  /** Firestore agent id. */
  agentId: string;
  /** Optional STT/TTS pipeline overrides. */
  pipeline?: VoqalPipelineConfig;
  /** Optional app-level payload handed to the brain. */
  payload?: Record<string, unknown>;
  /** ICE servers for the peer connection. Defaults to a public Google STUN. */
  iceServers?: RTCIceServer[];
  /** Connect immediately on mount. Default `false` — call {@link connect}. */
  autoConnect?: boolean;
  /**
   * Called for each RTVI server-message the bot pushes. The payload is already
   * unwrapped past the `{ data }` quirk — you receive the inner object directly.
   */
  onServerMessage?: (message: Record<string, unknown>) => void;
}

/** Value returned by {@link useVoqalSession}. */
export interface VoqalSessionHandle {
  /** The live `PipecatClient`, or `null` before connect / after disconnect. */
  client: PipecatClient | null;
  /** Transport connection lifecycle state. */
  connectionState: VoqalConnectionState;
  /** Coarse bot state (`idle` → `listening`/`thinking`/`speaking`). */
  botState: VoqalBotState;
  /** True while the local user is speaking (VAD). */
  isUserSpeaking: boolean;
  /** Last error message, or `null`. */
  error: string | null;
  /** Mint + connect a session. No-op if one is already active. */
  connect: () => Promise<void>;
  /** Tear down the active session. Safe to call repeatedly. */
  disconnect: () => Promise<void>;
  /** Enable or disable the local microphone. */
  enableMic: (enable: boolean) => void;
  /**
   * Send a custom app message from the browser to the brain. Arrives brain-side
   * as `on_app_event(session, AppEvent(name=type, data=data))`. Use it to keep
   * the brain in sync with on-screen state or to report a tap the user made
   * (e.g. `sendMessage("state_sync", { cart })`, `sendMessage("action_outcome",
   * { action_id, status: "done" })`). No-op before connect / after disconnect.
   */
  sendMessage: (type: string, data?: Record<string, unknown>) => void;
}

/** Defensive unwrap for the `RTVIEvent.ServerMessage` `{ data }` quirk. */
function unwrapServerMessage(raw: unknown): Record<string, unknown> {
  const obj = (raw ?? {}) as Record<string, unknown>;
  const inner = obj["data"] as Record<string, unknown> | undefined;
  return inner && "type" in inner ? inner : obj;
}

export function useVoqalSession(
  opts: UseVoqalSessionOptions
): VoqalSessionHandle {
  const clientRef = useRef<PipecatClient | null>(null);
  const [client, setClient] = useState<PipecatClient | null>(null);
  const [connectionState, setConnectionState] =
    useState<VoqalConnectionState>("idle");
  const [botState, setBotState] = useState<VoqalBotState>("idle");
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Keep the latest options in a ref so `connect` stays stable and always reads
  // current values without re-subscribing effects.
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const connect = useCallback(async () => {
    if (clientRef.current) return;
    const o = optsRef.current;

    setConnectionState("connecting");
    setBotState("idle");
    setIsUserSpeaking(false);
    setError(null);

    try {
      const { signalingUrl, token } = await createSession({
        apiBase: o.apiBase,
        tenantSlug: o.tenantSlug,
        publishableKey: o.publishableKey,
        agentId: o.agentId,
        pipeline: o.pipeline,
        payload: o.payload,
      });

      const transport = new VoqalWebRTCTransport({
        iceServers: o.iceServers ?? DEFAULT_ICE_SERVERS,
      });

      const pc = new PipecatClient({
        transport,
        enableMic: true,
        enableCam: false,
        callbacks: {
          onTransportStateChanged: (state) => {
            if (state === "connected" || state === "ready") {
              setConnectionState("connected");
            } else if (state === "connecting" || state === "authenticating") {
              setConnectionState("connecting");
            } else if (state === "error") {
              setConnectionState("error");
            } else if (state === "disconnected") {
              setConnectionState("disconnected");
            }
          },
          onBotReady: () => {
            setBotState("listening");
            setError(null);
          },
          onBotLlmStarted: () => {
            setBotState("thinking");
            setError(null);
          },
          onBotTtsStarted: () => setBotState("thinking"),
          // Fall back to listening if TTS ends without a speaking event.
          onBotTtsStopped: () =>
            setBotState((p) => (p === "thinking" ? "listening" : p)),
          onBotStartedSpeaking: () => setBotState("speaking"),
          onBotStoppedSpeaking: () => setBotState("listening"),
          onUserStartedSpeaking: () => setIsUserSpeaking(true),
          onUserStoppedSpeaking: () => setIsUserSpeaking(false),
          onServerMessage: (data) => {
            optsRef.current.onServerMessage?.(unwrapServerMessage(data));
          },
          onDisconnected: () => {
            setConnectionState((prev) =>
              prev === "error" ? prev : "disconnected"
            );
            setBotState("idle");
            setIsUserSpeaking(false);
          },
          onError: (msg) => {
            const text =
              (msg.data as { error?: string } | undefined)?.error ??
              "Unknown bot error";
            setError(text);
          },
        },
      });

      clientRef.current = pc;
      setClient(pc);
      await pc.connect({ connection_url: signalingUrl, token });
      setConnectionState("connected");
    } catch (err) {
      try {
        await clientRef.current?.disconnect();
      } catch {
        /* ignore */
      }
      clientRef.current = null;
      setClient(null);
      setConnectionState("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const disconnect = useCallback(async () => {
    const pc = clientRef.current;
    clientRef.current = null;
    if (pc) {
      try {
        await pc.disconnect();
      } catch {
        /* ignore */
      }
    }
    setClient(null);
    setConnectionState("idle");
    setBotState("idle");
    setIsUserSpeaking(false);
    setError(null);
  }, []);

  const enableMic = useCallback((enable: boolean) => {
    clientRef.current?.enableMic(enable);
  }, []);

  const sendMessage = useCallback(
    (type: string, data: Record<string, unknown> = {}) => {
      clientRef.current?.sendClientMessage(type, data);
    },
    []
  );

  useEffect(() => {
    if (optsRef.current.autoConnect) {
      connect().catch(() => {
        /* surfaced via error state */
      });
    }
    return () => {
      clientRef.current?.disconnect().catch(() => {
        /* ignore */
      });
      clientRef.current = null;
    };
    // Run once on mount; connect/disconnect are stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    client,
    connectionState,
    botState,
    isUserSpeaking,
    error,
    connect,
    disconnect,
    enableMic,
    sendMessage,
  };
}
