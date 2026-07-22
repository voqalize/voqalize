/**
 * @voqalize/client-react — embed a Voqalize voice agent in a React app.
 *
 * Three layers, from lowest to highest:
 *   - {@link VoqalWebRTCTransport} — the pipecat `Transport` (WS signaling + P2P
 *     WebRTC). Use directly with a raw `PipecatClient` for full control.
 *   - {@link createSession} — mint + start a session with a `pk_` key.
 *   - {@link useVoqalSession} / {@link VoqalAgent} — the React surface that ties
 *     the two together and manages the `PipecatClient` lifecycle.
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
