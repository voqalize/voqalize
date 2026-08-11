/**
 * <VoqalAgent/> — drop-in voice agent embed.
 *
 * The smallest possible surface: give it an `apiBase`, `publishableKey`, and
 * `agentId`, and it mints a session, connects, plays the
 * agent's audio, and renders a minimal status + mic/end control bar.
 *
 * For a custom UI, pass a render-prop `children` — you get the full
 * {@link VoqalSessionHandle} and own all markup (audio playback is still wired
 * for you). Built on {@link useVoqalSession}.
 */

import { useEffect, useRef, type ReactNode } from "react";
import {
  PipecatClientProvider,
  usePipecatClientMediaTrack,
} from "@pipecat-ai/client-react";
import {
  useVoqalSession,
  type UseVoqalSessionOptions,
  type VoqalSessionHandle,
} from "./useVoqalSession";

/** Props for {@link VoqalAgent}. */
export interface VoqalAgentProps extends UseVoqalSessionOptions {
  /**
   * Render-prop for a custom UI. Receives the live session handle. When
   * provided, the built-in status bar is not rendered (audio is still wired).
   */
  children?: (session: VoqalSessionHandle) => ReactNode;
  /** Optional className applied to the default UI wrapper. */
  className?: string;
}

/** Hidden `<audio>` element that plays the bot's audio track. */
function BotAudio() {
  const track = usePipecatClientMediaTrack("audio", "bot");
  const ref = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (track) {
      el.srcObject = new MediaStream([track]);
      el.play().catch(() => {
        /* autoplay may be blocked until a user gesture — ignore */
      });
    } else {
      el.srcObject = null;
    }
  }, [track]);

  return <audio ref={ref} autoPlay playsInline hidden />;
}

const STATUS_LABEL: Record<string, string> = {
  idle: "Ready",
  connecting: "Connecting…",
  // Not "Connecting…" — the browser is holding a permission prompt open and
  // will hold it forever. This is the one status that asks the user to act.
  "awaiting-microphone": "Allow microphone access…",
  connected: "Live",
  disconnected: "Disconnected",
  error: "Error",
};

/** Minimal built-in control bar, used when no render-prop is supplied. */
function DefaultUI({ session }: { session: VoqalSessionHandle }) {
  const { connectionState, botState, error, disconnect, enableMic } = session;
  const micRef = useRef(true);

  const toggleMic = () => {
    micRef.current = !micRef.current;
    enableMic(micRef.current);
  };

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 10,
        padding: "10px 14px",
        borderRadius: 12,
        background: "#111827",
        color: "#e5e7eb",
        font: "500 13px system-ui, sans-serif",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background:
            connectionState === "connected"
              ? "#22c55e"
              : connectionState === "error"
                ? "#ef4444"
                : "#f59e0b",
        }}
      />
      <span>
        {error
          ? error
          : connectionState === "connected"
            ? botState === "thinking"
              ? "Thinking…"
              : botState === "speaking"
                ? "Speaking"
                : "Listening…"
            : (STATUS_LABEL[connectionState] ?? connectionState)}
      </span>
      {connectionState === "connected" && (
        <>
          <button onClick={toggleMic} style={btnStyle} type="button">
            Mute
          </button>
          <button
            onClick={() => {
              void disconnect();
            }}
            style={{ ...btnStyle, background: "#7f1d1d" }}
            type="button"
          >
            End
          </button>
        </>
      )}
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  border: "none",
  borderRadius: 8,
  padding: "5px 10px",
  background: "#374151",
  color: "#e5e7eb",
  font: "600 12px system-ui, sans-serif",
  cursor: "pointer",
};

export function VoqalAgent({ children, className, ...options }: VoqalAgentProps) {
  const session = useVoqalSession({ autoConnect: true, ...options });

  const body = children ? (
    children(session)
  ) : (
    <DefaultUI session={session} />
  );

  if (!session.client) {
    return <div className={className}>{body}</div>;
  }

  return (
    <div className={className}>
      <PipecatClientProvider client={session.client}>
        <BotAudio />
        {body}
      </PipecatClientProvider>
    </div>
  );
}
