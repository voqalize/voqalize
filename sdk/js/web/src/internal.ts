/**
 * Internal to `@voqalize/web`: the session adapter the widget's elements
 * read. Not stable API, and not exported from the package root — it may
 * change in any release without notice. The stable session is
 * `VoqalizeClient`, designed separately.
 */

import type { CaptionsController } from "./controllers/captions.js";
import type { WidgetSession } from "./session/adapter.js";

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
export { InstantStartMediaManager, type MediaPlatformOptions, isIOS } from "./session/media.js";

/** Drive a captions controller from a session's agent and visitor events. Returns the unbind. */
export function bindCaptions(session: WidgetSession, captions: CaptionsController): () => void {
  const offs = [
    session.on("agentSentence", (text) => captions.agentSentence(text)),
    session.on("agentWord", (text) => captions.agentWord(text)),
    session.on("agentStarted", () => captions.agentStarted()),
    session.on("agentStopped", () => captions.agentStopped()),
    session.on("userTranscript", (text, final) => captions.userTranscript(text, final)),
  ];
  return () => {
    for (const off of offs) off();
  };
}
