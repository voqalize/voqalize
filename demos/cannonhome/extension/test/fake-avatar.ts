/**
 * The avatar, as the extension the end-to-end tests load has it: no runtime
 * from the avatar's host, only a record of what the page asked of it.
 */

import type { PipecatClient } from "@pipecat-ai/client-js";

export interface AvatarInstance {
  destroy(): void;
}

export function createAvatar(opts: { mount: HTMLElement; client: PipecatClient; character: string }): AvatarInstance {
  const el = document.createElement("div");
  el.dataset.fakeAvatar = opts.character;
  opts.mount.appendChild(el);
  // What reaches the face from the holder's relay, counted.
  const seen: Record<string, number> = {};
  for (const name of ["botStartedSpeaking", "botStoppedSpeaking", "connected", "botReady", "serverMessage"]) {
    opts.client.on(name as never, (() => {
      seen[name] = (seen[name] ?? 0) + 1;
      el.dataset.seen = JSON.stringify(seen);
    }) as never);
  }
  return { destroy: () => el.remove() };
}

export function preloadAvatar(_character: string): void {}

export async function listCharacters(): Promise<{ name: string; still?: string }[]> {
  return [];
}
