/**
 * What a page that arrives in the middle of a reply needs to draw it: the
 * avatar's messages for the reply in progress, kept by the holder and sent to
 * each face a page makes, when it asks (`holder.ts`, `follow.ts`).
 *
 * The voice runtime sends a reply's mouth cues as the words are made, which is
 * seconds ahead of the audio, and sends each again only to a browser that
 * reconnects. A page load in the offscreen holder's call is no reconnect: the
 * call goes on, and the next page's face would hear only what comes after it
 * arrives. A reply whose cues had all been sent by then played its remaining
 * words over a still mouth (dev session 6956bc76: 10 s of a 15.5 s reply).
 *
 * So this keeps what the runtime keeps for a reconnect: the avatar's state,
 * and for each reply still being heard, where its audio sits on the stream
 * (`sync`), its cues and its end, in arrival order; and whether he is
 * speaking. A reply is let go as the face lets it go: on `botStoppedSpeaking`
 * once its end is known, and every reply on an interruption or on the
 * visitor's next turn while he is quiet.
 */

import type { ToPage } from "./protocol";

/** Contexts kept at most; a reply is a handful of sentences. */
const MAX_CONTEXTS = 8;
/** `sync` messages kept per context: one at its start and one per stall. */
const MAX_SYNCS = 32;

type Avatar = { type?: unknown; cmd?: unknown; ctx?: unknown; id?: unknown };

interface Kept {
  /** In arrival order: its `sync`s, cues and end, as they went to the pages. */
  sent: ToPage[];
  syncs: number;
  ended: boolean;
}

/** The avatar's command inside a server message, as the avatar unwraps it. */
function avatarOf(data: unknown): Avatar | null {
  const obj = (data ?? {}) as Record<string, unknown>;
  const inner = obj["data"] as Avatar | undefined;
  const msg = (inner && typeof inner === "object" && "type" in inner ? inner : obj) as Avatar;
  return msg.type === "avatar" && typeof msg.cmd === "string" ? msg : null;
}

export class CatchUp {
  private state: ToPage | null = null;
  private speaking: ToPage | null = null;
  private readonly contexts = new Map<string, Kept>();

  /** One message as it goes to the pages. */
  saw(msg: ToPage): void {
    if (msg.k === "sync") return this.context(msg.msg, msg);
    if (msg.k !== "ev") return;
    if (msg.name === "botStartedSpeaking") {
      this.speaking = msg;
      return;
    }
    if (msg.name === "botStoppedSpeaking") {
      this.speaking = null;
      for (const [ctx, kept] of this.contexts) if (kept.ended) this.contexts.delete(ctx);
      return;
    }
    // The visitor's next turn while he is quiet: what he had not yet said
    // will not be said (the runtime tells the face of a cut only while he
    // speaks).
    if (msg.name === "userStartedSpeaking") {
      if (!this.speaking) this.contexts.clear();
      return;
    }
    if (msg.name !== "serverMessage") return;
    const avatar = avatarOf(msg.data);
    if (!avatar) return;
    if (avatar.cmd === "state") this.state = msg;
    else if (avatar.cmd === "action" && avatar.id === "RESPONSE_INTERRUPTED") this.contexts.clear();
    else this.context(avatar, msg);
  }

  /** What a page that has just said hello is sent: the state, then each reply
   *  still being heard, then whether he is speaking. */
  replay(): ToPage[] {
    const out: ToPage[] = [];
    if (this.state) out.push(this.state);
    for (const kept of this.contexts.values()) out.push(...kept.sent);
    if (this.speaking) out.push(this.speaking);
    return out;
  }

  /** The call is over. */
  clear(): void {
    this.state = null;
    this.speaking = null;
    this.contexts.clear();
  }

  private context(avatar: unknown, msg: ToPage): void {
    const { cmd, ctx } = (avatar ?? {}) as Avatar;
    if (typeof ctx !== "string" || (cmd !== "cues" && cmd !== "sync" && cmd !== "end")) return;
    let kept = this.contexts.get(ctx);
    if (!kept) {
      kept = { sent: [], syncs: 0, ended: false };
      this.contexts.set(ctx, kept);
      if (this.contexts.size > MAX_CONTEXTS) this.contexts.delete(this.contexts.keys().next().value!);
    }
    if (cmd === "sync" && ++kept.syncs > MAX_SYNCS) return;
    if (cmd === "end") kept.ended = true;
    kept.sent.push(msg);
  }
}
