/**
 * The avatar, as the extension the end-to-end tests load has it: no runtime
 * from the avatar's host, only a record of what the page asked of it.
 *
 * It reads the mouth clock as the avatar does: every poll, the newest
 * delivery the client's receiver reports (`getSynchronizationSources()`),
 * kept in `window.__faceReads` with the page's epoch time of the read.
 *
 * Like the avatar, it starts listening only a moment after it is made (the
 * avatar loads its runtime first), and it keeps, in `window.__faceSaw`, the
 * avatar's messages and the speaking events in the order they reach it.
 */

import type { PipecatClient } from "@pipecat-ai/client-js";

/** The avatar's own poll of the stream. */
const POLL_MS = 23;
/** How long after it is made the face starts listening. */
const ATTACH_MS = 300;

/** One thing the face heard: an avatar command (with its context, the
 *  first cue's offset and a sync's place in the reply), or a speaking event. */
interface FaceSaw {
  what: string;
  ctx?: string;
  from_ms?: number;
  at_ms?: number;
}

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
  // A face that draws: a canvas with something on it, which the page waits
  // for before it fades the face in.
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 16;
  const g = canvas.getContext("2d")!;
  g.fillStyle = "#a01a1a";
  g.fillRect(0, 0, 16, 16);
  el.appendChild(canvas);
  opts.mount.appendChild(el);
  // What reaches the face from the holder's relay, counted, and in order.
  const seen: Record<string, number> = {};
  const saw: FaceSaw[] = ((window as unknown as { __faceSaw?: FaceSaw[] }).__faceSaw = []);
  const heard = (msg: unknown) => {
    const m = (msg ?? {}) as { type?: string; cmd?: string; ctx?: string; from_ms?: number; at_ms?: number };
    if (m.type === "avatar" && m.cmd) saw.push({ what: m.cmd, ctx: m.ctx, from_ms: m.from_ms, at_ms: m.at_ms });
  };
  const attach = setTimeout(() => {
    for (const name of ["botStartedSpeaking", "botStoppedSpeaking", "connected", "botReady", "serverMessage"]) {
      opts.client.on(name as never, ((data: unknown) => {
        seen[name] = (seen[name] ?? 0) + 1;
        el.dataset.seen = JSON.stringify(seen);
        if (name === "serverMessage") heard(data);
        else if (name.startsWith("bot") && name.endsWith("Speaking")) saw.push({ what: name });
      }) as never);
    }
    // The avatar's sync channel, as the avatar opens it.
    const pc = (opts.client as unknown as { transport?: { pc?: { createDataChannel?: (l: string, i: unknown) => RTCDataChannel } | null } })
      .transport?.pc;
    const channel = pc?.createDataChannel?.("avatar-sync", { negotiated: true, id: 200, ordered: false, maxRetransmits: 0 });
    if (channel) channel.onmessage = (e: MessageEvent) => heard(JSON.parse(String(e.data)));
  }, ATTACH_MS);
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
      clearTimeout(attach);
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
