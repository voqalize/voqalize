import type { SessionEvents } from "../session/adapter.js";
import type { CaptionsController } from "./captions.js";

/** Anything that emits the session's caption events; `WidgetSession` does. */
export interface CaptionEventSource {
  on<K extends keyof SessionEvents>(event: K, listener: SessionEvents[K]): () => void;
}

/** Drive a captions controller from a session's agent and visitor events. Returns the unbind. */
export function bindCaptions(session: CaptionEventSource, captions: CaptionsController): () => void {
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
