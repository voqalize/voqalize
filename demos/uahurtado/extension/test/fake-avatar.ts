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
  // A face that draws: a canvas with something on it, which the page keeps
  // the last frame of.
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 16;
  const g = canvas.getContext("2d")!;
  g.fillStyle = "#a01a1a";
  g.fillRect(0, 0, 16, 16);
  el.appendChild(canvas);
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

export function preloadAvatar(character: string): { character: string; ready: Promise<void> } {
  return { character, ready: Promise.resolve() };
}

export async function listCharacters(): Promise<{ name: string; still?: string }[]> {
  return [];
}
