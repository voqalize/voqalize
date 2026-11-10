/**
 * Internal to `@voqalize/web`: the session adapter the widget's elements
 * read. Not stable API, and not exported from the package root — it may
 * change in any release without notice. The stable session is
 * `VoqalizeClient`, designed separately.
 */

export {
  type AgentState,
  type ClientFactoryArgs,
  type ClientLike,
  DEFAULT_API_BASE,
  type DeviceSnapshot,
  type EndReason,
  type MediaManagerLike,
  type MintOptions,
  type SessionEvents,
  type SessionOptions,
  type SessionResponse,
  type SessionSnapshot,
  type SessionSource,
  type SessionStatus,
  WidgetSession,
  mintSession,
  withRealHeaders,
} from "./session/adapter.js";
export { TONE_AGAIN_MS, type TonePlayer, createTonePlayer } from "./session/tone.js";

export { bindCaptions, type CaptionEventSource } from "./controllers/bind-captions.js";
