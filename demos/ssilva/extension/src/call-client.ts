/**
 * The call itself, as the holder makes it: stock pipecat on
 * `@voqalize/client-transport`'s media, and the extension's microphone
 * permission. The end-to-end tests build the extension with a stand-in for
 * this module (`test/fake-call-client.ts`), so the holder's routing can be
 * driven without a network.
 */

import { PipecatClient, type PipecatClientOptions } from "@pipecat-ai/client-js";
import { createVoqalizeTransport, VoqalizeMediaManager } from "@voqalize/client-transport";

import type { MicState } from "./protocol";

export function makeClient(output: HTMLAudioElement, callbacks: PipecatClientOptions["callbacks"]): PipecatClient {
  // Local media on `@voqalize/client-transport`, not pipecat's default, which
  // loads a third-party call machine.
  const media = new VoqalizeMediaManager();
  media.bindOutputElement(output);
  const transport = createVoqalizeTransport({ mediaManager: media });
  return new PipecatClient({ transport, enableMic: true, enableCam: false, callbacks });
}

/** The extension's own microphone permission, which is what this document's
 *  `getUserMedia` is held to (never ssilva.cl's). */
export async function micState(): Promise<MicState> {
  try {
    const status = await navigator.permissions.query({ name: "microphone" as PermissionName });
    return status.state;
  } catch {
    return "prompt";
  }
}

/** The tests' hooks into the holder; none in the extension. */
export function testHooks(_holder: unknown): void {}
