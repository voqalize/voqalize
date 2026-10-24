/**
 * The avatar, as the extension the end-to-end tests load has it: no runtime
 * from the avatar's host, only a record of what the page asked of it.
 *
 * It reads the mouth clock as the avatar does: every poll, the newest
 * delivery the client's receiver reports (`getSynchronizationSources()`),
 * kept in `window.__faceReads` with the page's epoch time of the read.
 */

import type { PipecatClient } from "@pipecat-ai/client-js";

/** The avatar's own poll of the stream. */
const POLL_MS = 23;

/** One read of the mouth clock: when (epoch ms), and the delivery it saw. */
interface FaceRead {
  at: number;
  timestamp: number | null;
}

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
  const reads: FaceRead[] = ((window as unknown as { __faceReads?: FaceRead[] }).__faceReads ??= []);
  const poll = setInterval(() => {
    const pc = (opts.client as unknown as { transport?: { pc?: { getReceivers?: () => RTCRtpReceiver[] } | null } })
      .transport?.pc;
    const receiver = pc?.getReceivers?.().find((r) => r.track?.kind === "audio");
    let newest: RTCRtpSynchronizationSource | null = null;
    for (const s of receiver?.getSynchronizationSources() ?? []) if (!newest || s.timestamp > newest.timestamp) newest = s;
    reads.push({ at: performance.timeOrigin + performance.now(), timestamp: newest?.timestamp ?? null });
    if (reads.length > 4000) reads.splice(0, reads.length - 4000);
  }, POLL_MS);
  return {
    destroy: () => {
      clearInterval(poll);
      el.remove();
    },
  };
}

export function preloadAvatar(character: string): { character: string; ready: Promise<void> } {
  return { character, ready: Promise.resolve() };
}

export async function listCharacters(): Promise<{ name: string; still?: string }[]> {
  return [];
}
