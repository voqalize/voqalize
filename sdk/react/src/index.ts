/**
 * @voqalize/client-react — mint a Voqalize session for a pipecat client.
 *
 * This package is the connection step and nothing else. A Voqalize call *is* a
 * pipecat call: the media transport is pipecat's own `SmallWebRTCTransport`, the
 * events are RTVI's, and the brain's UI commands arrive at pipecat's
 * `useUICommandHandler`. None of that needs a wrapper from us, so none is shipped.
 *
 * What is ours is step one of pipecat's two-step connect — turning a publishable
 * key and an agent id into the offer endpoint and token a transport can dial:
 *
 * ```ts
 * const client = new PipecatClient({
 *   transport: new SmallWebRTCTransport(),
 *   enableMic: true,
 * });
 * await client.connect(await createSession({ apiBase, publishableKey, agentId }));
 * ```
 *
 * {@link toConnectParams} is the same translation over a response you fetched
 * yourself — for apps that mint the session on their own server.
 */

export {
  createSession,
  toConnectParams,
  VoqalSessionError,
  type CreateSessionOptions,
  type VoqalConnectParams,
  type VoqalPipelineConfig,
} from "./createSession";
