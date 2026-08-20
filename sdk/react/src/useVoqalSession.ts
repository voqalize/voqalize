/**
 * useVoqalSession — the full lifecycle of one Voqalize voice session in a hook.
 *
 * Encapsulates: acquire the microphone → mint a session → build pipecat's
 * `SmallWebRTCTransport` → drive a `PipecatClient` → surface connection state, a
 * coarse bot state, mic control, and normalized server messages.
 *
 * ## Two ways to mint, one way to connect
 *
 * Connecting is pipecat's two-step: ask something that holds a credential
 * *where the bot is*, then negotiate WebRTC against the address you were given.
 * Only the first step differs.
 *
 * - **`publishableKey`** — this hook performs step one against the Voqalize
 *   control plane with a `pk_` key. Nothing secret ships in the page; a `pk_` is
 *   scoped to one agent and constrained by an origin allowlist.
 * - **`connectEndpoint`** — *your* backend performs step one, holding whatever
 *   credential it likes, and returns the same connection parameters. Use this
 *   the moment the decision to start a call depends on something the browser
 *   must not be trusted with: who the caller is, whether they have credit, which
 *   agent they get.
 *
 * Both paths end at the same `PipecatClient.connect(...)`, because the address
 * is a URL and a token either way. Keep it thin: it owns a single
 * `PipecatClient` at a time and tears it down on unmount.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { MicrophoneError, requestMicrophone } from "./microphone";
import {
  createSession,
  toConnectParams,
  VoqalSessionError,
  type VoqalConnectParams,
  type VoqalPipelineConfig,
} from "./createSession";

/**
 * Transport-level connection lifecycle.
 *
 * `awaiting-microphone` is its own state rather than a flavour of `connecting`
 * because the two need opposite things from the user: `connecting` means wait,
 * and this one means *do something* — the browser is holding a permission
 * prompt open and will hold it indefinitely.
 */
export type VoqalConnectionState =
  | "idle"
  | "connecting"
  | "awaiting-microphone"
  | "connected"
  | "disconnected"
  | "error";

/** Coarse conversational state of the agent, derived from RTVI events. */
export type VoqalBotState = "idle" | "listening" | "thinking" | "speaking";

const DEFAULT_ICE_SERVERS: RTCIceServer[] = [
  { urls: "stun:stun.l.google.com:19302" },
];

/** Options shared by both ways of starting a session. */
export interface VoqalSessionOptionsBase {
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

/** Mint in the browser with a publishable key. */
export interface VoqalPublishableKeyOptions extends VoqalSessionOptionsBase {
  /** Versioned API root, e.g. `"/api/v1"`. */
  apiBase: string;
  /** Publishable (`pk_...`) key. */
  publishableKey: string;
  /** Firestore agent id. */
  agentId: string;
  /** Optional STT/TTS pipeline overrides. */
  pipeline?: VoqalPipelineConfig;
  /** Optional app-level payload handed to the brain. */
  payload?: Record<string, unknown>;
}

/** Mint on your own backend, which returns the connection parameters. */
export interface VoqalConnectEndpointOptions extends VoqalSessionOptionsBase {
  /**
   * A route on *your* server that starts a session and returns its
   * `connect_params` — see {@link toConnectParams} for the shape. Called with
   * `POST`, and with `credentials: "include"` so a session cookie you already
   * set is what authorizes it.
   */
  connectEndpoint: string;
  /** Extra headers on the mint request (a CSRF token, your own bearer). */
  connectHeaders?: Record<string, string>;
  /** JSON body for the mint request. Yours to define; we do not read it. */
  connectData?: Record<string, unknown>;
}

/** Options for {@link useVoqalSession}. */
export type UseVoqalSessionOptions =
  | VoqalPublishableKeyOptions
  | VoqalConnectEndpointOptions;

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
  /**
   * Set when the failure was the microphone rather than the service.
   *
   * The distinction is the whole point: a blocked microphone is something the
   * person in front of the browser can fix in one click, and telling them to
   * "check your connection" instead sends them somewhere there is nothing to
   * find. Branch on `.problem`; `.message` is already written for them.
   */
  microphoneError: MicrophoneError | null;
  /** Mint + connect a session. No-op if one is already active. */
  connect: () => Promise<void>;
  /** Tear down the active session. Safe to call repeatedly. */
  disconnect: () => Promise<void>;
  /** Enable or disable the local microphone. */
  enableMic: (enable: boolean) => void;
  /**
   * Send a custom app message from the browser to the brain. Arrives brain-side
   * as `on_client_message(session, ClientMessage(type=type, data=data))`. Use it to keep
   * the brain in sync with on-screen state or to report a tap the user made
   * (e.g. `sendMessage("state_sync", { cart })`, `sendMessage("action_result",
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

function hasConnectEndpoint(
  o: UseVoqalSessionOptions
): o is VoqalConnectEndpointOptions {
  return typeof (o as VoqalConnectEndpointOptions).connectEndpoint === "string";
}

/**
 * Step one via the caller's own backend.
 *
 * Deliberately a plain `fetch` rather than pipecat's `startBotAndConnect`: that
 * path feeds the JSON response straight to the transport, where `headers`
 * arrives as a plain object and pipecat's `headers.entries()` throws. Everything
 * a server returns goes through {@link toConnectParams} first, on both paths.
 */
async function mintFromEndpoint(
  o: VoqalConnectEndpointOptions
): Promise<VoqalConnectParams> {
  let res: Response;
  try {
    res = await fetch(o.connectEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(o.connectHeaders ?? {}),
      },
      // Your route, your session: a cookie you already set is the natural way
      // to authorize this, and omitting it would force every embed to invent a
      // second credential for the browser to hold.
      credentials: "include",
      body: JSON.stringify(o.connectData ?? {}),
    });
  } catch (err) {
    throw new VoqalSessionError(
      `connectEndpoint: network error — ${(err as Error).message}`,
      0
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.text()).slice(0, 500);
    } catch {
      /* ignore */
    }
    throw new VoqalSessionError(
      `connectEndpoint: session start failed (${res.status})${detail ? `: ${detail}` : ""}`,
      res.status
    );
  }

  try {
    return toConnectParams(await res.json());
  } catch (err) {
    if (err instanceof VoqalSessionError) {
      throw new VoqalSessionError(err.message, res.status);
    }
    throw new VoqalSessionError(
      `connectEndpoint: could not parse response — ${(err as Error).message}`,
      res.status
    );
  }
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
  const [microphoneError, setMicrophoneError] = useState<MicrophoneError | null>(
    null
  );

  // Keep the latest options in a ref so `connect` stays stable and always reads
  // current values without re-subscribing effects.
  const optsRef = useRef(opts);
  optsRef.current = opts;

  // `clientRef` alone cannot guard re-entry: it is only set after the session is
  // minted, so a teardown-and-remount inside that window (React StrictMode does
  // exactly this) starts a second session while the first is still in flight. The
  // generation counter lets the stale attempt notice it lost and bow out.
  const generationRef = useRef(0);

  const connect = useCallback(async () => {
    if (clientRef.current) return;
    const o = optsRef.current;
    const generation = generationRef.current;

    setConnectionState("connecting");
    setBotState("idle");
    setIsUserSpeaking(false);
    setError(null);
    setMicrophoneError(null);

    try {
      // Ask for the microphone first, and on our own terms. The transport's
      // media manager will ask again a moment later, but by then the permission
      // is granted and no prompt appears — what this buys is the *typed*
      // failure: a blocked microphone, a prompt nobody answered, an insecure
      // origin. Left to the transport those all arrive as one opaque rejection
      // long after the session has been minted and paid for.
      const mic = await requestMicrophone({
        onWaiting: () => {
          // Only from `connecting` — by the time the mic is being re-acquired
          // mid-call the connection state means something else.
          setConnectionState((prev) =>
            prev === "connecting" ? "awaiting-microphone" : prev
          );
        },
      });
      if (generation !== generationRef.current) {
        if (!(mic instanceof MicrophoneError)) {
          mic.getTracks().forEach((t) => t.stop());
        }
        return;
      }
      if (mic instanceof MicrophoneError) throw mic;
      // Release it immediately: the transport opens its own capture, and two
      // live captures of one device is how a caller ends up muted.
      mic.getTracks().forEach((t) => t.stop());
      setConnectionState("connecting");

      const connectParams = hasConnectEndpoint(o)
        ? await mintFromEndpoint(o)
        : await createSession({
            apiBase: o.apiBase,
            publishableKey: o.publishableKey,
            agentId: o.agentId,
            pipeline: o.pipeline,
            payload: o.payload,
          });
      if (generation !== generationRef.current) return;

      const transport = new SmallWebRTCTransport({
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
      await pc.connect(connectParams);
      if (generation !== generationRef.current) {
        await pc.disconnect().catch(() => {
          /* ignore */
        });
        return;
      }
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
      if (err instanceof MicrophoneError) setMicrophoneError(err);
    }
  }, []);

  const disconnect = useCallback(async () => {
    generationRef.current += 1;
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
    setMicrophoneError(null);
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
      generationRef.current += 1;
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
    microphoneError,
    connect,
    disconnect,
    enableMic,
    sendMessage,
  };
}
