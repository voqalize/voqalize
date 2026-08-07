/**
 * @voqalize/client-react — embed a Voqalize voice agent in a React app.
 *
 * Three layers, from lowest to highest:
 *   - {@link VoqalWebRTCTransport} — the pipecat `Transport` (WS signaling + P2P
 *     WebRTC). Use directly with a raw `PipecatClient` for full control.
 *   - {@link createSession} — mint + start a session with a `pk_` key.
 *   - {@link useVoqalSession} / {@link VoqalAgent} — the React surface that ties
 *     the two together and manages the `PipecatClient` lifecycle.
 *   - {@link useUiCommand} — the other direction: dispatch the brain's
 *     `ui_command`s to typed per-action handlers instead of a hand-rolled switch.
 *
 * Plus two pieces of UI, one for each end of a call:
 *   - {@link PreCallGate} — the notice-and-consent screen shown before a
 *     microphone opens. Structure only; every word is yours, because what has to
 *     be disclosed is your call to make, not ours.
 *   - {@link AmbientPresence} — the full-viewport glow that makes the agent read
 *     as a property of the page rather than a widget in a corner.
 *
 * Neither ships a stylesheet — drop them in and pass a palette.
 */

export {
  VoqalWebRTCTransport,
  type VoqalWebRTCTransportOptions,
  type VoqalConnectParams,
} from "./transport";

export {
  createSession,
  VoqalSessionError,
  type CreateSessionOptions,
  type VoqalSession,
  type VoqalPipelineConfig,
} from "./createSession";

export {
  useVoqalSession,
  type UseVoqalSessionOptions,
  type VoqalSessionHandle,
  type VoqalConnectionState,
  type VoqalBotState,
} from "./useVoqalSession";

export { VoqalAgent, type VoqalAgentProps } from "./VoqalAgent";

export {
  useUiCommand,
  createUiCommandHandlers,
  uiCommandArgs,
  type UiCommand,
  type UiCommandArgs,
  type UiCommandHandlers,
} from "./useUiCommand";

export {
  AmbientPresence,
  type AmbientPresenceProps,
  type AmbientPresencePalette,
  type AmbientPresenceBeam,
} from "./AmbientPresence";

export { PreCallGate, type PreCallGateProps } from "./PreCallGate";
