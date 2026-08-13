/**
 * @voqalize/client-react — embed a Voqalize voice agent in a React app.
 *
 * The media transport is pipecat's own `SmallWebRTCTransport`, not one of ours:
 * a session's connection details name an offer endpoint and carry a token, which
 * is exactly what it already speaks. What this package adds is everything
 * *around* the call.
 *
 * Three layers, from lowest to highest:
 *   - {@link createSession} / {@link toConnectParams} — step one of pipecat's
 *     two-step connect: mint a session and turn the answer into transport-ready
 *     parameters. Use these directly with a raw `PipecatClient` for full control.
 *   - {@link useVoqalSession} / {@link VoqalAgent} — the React surface that ties
 *     minting and connecting together and manages the `PipecatClient` lifecycle.
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
  MicrophoneError,
  requestMicrophone,
  type MicrophoneProblem,
} from "./microphone";

export {
  createSession,
  toConnectParams,
  VoqalSessionError,
  type CreateSessionOptions,
  type VoqalConnectParams,
  type VoqalPipelineConfig,
} from "./createSession";

export {
  useVoqalSession,
  type UseVoqalSessionOptions,
  type VoqalSessionOptionsBase,
  type VoqalPublishableKeyOptions,
  type VoqalConnectEndpointOptions,
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
