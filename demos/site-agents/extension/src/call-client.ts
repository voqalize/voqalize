/**
 * The call itself, as the holder makes it: stock pipecat on
 * `@voqalize/client-transport`'s media, and the extension's microphone
 * permission. What the Site Agent's brain speaks differently from a demo brain
 * is translated around this client, in `holder.ts`.
 */

import { PipecatClient, type PipecatClientOptions } from "@pipecat-ai/client-js";
import type { MicState } from "@voqalize/stage/extension";
import { createVoqalizeTransport, VoqalizeMediaManager } from "@voqalize/client-transport";

export function makeClient(output: HTMLAudioElement, callbacks: PipecatClientOptions["callbacks"]): PipecatClient {
  // Local media on `@voqalize/client-transport`, not pipecat's default, which
  // loads a third-party call machine.
  const media = new VoqalizeMediaManager();
  media.bindOutputElement(output);
  const transport = createVoqalizeTransport({ mediaManager: media });
  return new PipecatClient({ transport, enableMic: true, enableCam: false, callbacks });
}

/** The extension's own microphone permission, which is what the holder's
 *  `getUserMedia` is held to (never the site's). */
export async function micState(): Promise<MicState> {
  try {
    const status = await navigator.permissions.query({ name: "microphone" as PermissionName });
    return status.state;
  } catch {
    return "prompt";
  }
}
