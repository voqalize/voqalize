/**
 * What the holder sends a page that arrives in the middle of a reply
 * (`CatchUp`, `src/extension/catch-up.ts`): the state, each reply still being heard, whether he is
 * speaking, and nothing of a reply that is over. No browser.
 */

import { describe, expect, it as test } from "vitest";

import { CatchUp } from "../src/extension/catch-up";
import type { ToPage } from "../src/extension/protocol";

const avatar = (cmd: Record<string, unknown>): ToPage => ({ k: "ev", name: "serverMessage", data: { type: "avatar", ...cmd } });
const ev = (name: string): ToPage => ({ k: "ev", name, data: {} });
const sync = (ctx: string, at_ms = 0): ToPage => ({ k: "sync", msg: { type: "avatar", cmd: "sync", ctx, at_ms, rtp: 4800, rate: 48000 } });
const end = (ctx: string, at_ms: number): ToPage => ({ k: "sync", msg: { type: "avatar", cmd: "end", ctx, at_ms } });
const cues = (ctx: string, from_ms: number): ToPage => avatar({ cmd: "cues", ctx, from_ms, cues: [{ t: from_ms, v: "B" }] });

function fed(...msgs: ToPage[]): CatchUp {
  const c = new CatchUp();
  for (const m of msgs) c.saw(m);
  return c;
}

describe("what a page arriving mid-reply is sent", () => {
  test("the state, the reply being heard (its place on the stream from its resyncs, every cue chunk, in order), then that he is speaking", () => {
    const state = avatar({ cmd: "state", state: "WORKING" });
    const c = fed(state, cues("a", 0), sync("a"), ev("botStartedSpeaking"), cues("a", 900), sync("a", 1000), avatar({ cmd: "action", id: "ACKNOWLEDGE" }));
    expect(c.replay()).toEqual([state, cues("a", 0), cues("a", 900), sync("a", 1000), ev("botStartedSpeaking")]);
  });

  test("never the reply's start (a sync at 0 ms), from either road: a face handed it would think it heard the reply begin; the resyncs place it", () => {
    const viaServer = (ctx: string, at_ms: number) => avatar({ cmd: "sync", ctx, at_ms, rtp: 4800, rate: 48000 });
    const c = fed(ev("botStartedSpeaking"), sync("a", 0), viaServer("a", 0), cues("a", 0), sync("a", 1000), viaServer("a", 1000));
    expect(c.replay()).toEqual([cues("a", 0), sync("a", 1000), viaServer("a", 1000), ev("botStartedSpeaking")]);
  });

  test("the RTVI envelope the client may hand over is read the way the avatar reads it", () => {
    const wrapped: ToPage = { k: "ev", name: "serverMessage", data: { type: "server-message", data: { type: "avatar", cmd: "cues", ctx: "a", from_ms: 0, cues: [] } } };
    expect(fed(wrapped).replay()).toEqual([wrapped]);
  });

  test("a reply whose end is known is let go when he stops speaking; one still going is kept", () => {
    const c = fed(ev("botStartedSpeaking"), sync("a", 1000), cues("a", 0), end("a", 1600), sync("b", 1000), cues("b", 0), ev("botStoppedSpeaking"));
    expect(c.replay()).toEqual([sync("b", 1000), cues("b", 0)]);
  });

  test("an interruption lets every reply go", () => {
    const c = fed(ev("botStartedSpeaking"), sync("a"), cues("a", 0), avatar({ cmd: "action", id: "RESPONSE_INTERRUPTED" }));
    expect(c.replay()).toEqual([ev("botStartedSpeaking")]);
  });

  test("the visitor's next turn while he is quiet lets a reply never heard go; while he speaks it does not", () => {
    expect(fed(cues("a", 0), ev("userStartedSpeaking")).replay()).toEqual([]);
    const speaking = fed(ev("botStartedSpeaking"), sync("a", 1000), cues("a", 0), ev("userStartedSpeaking"));
    expect(speaking.replay()).toEqual([sync("a", 1000), cues("a", 0), ev("botStartedSpeaking")]);
  });

  test("nothing else is kept: the relayed clock, playout, other events, other apps' messages", () => {
    const c = fed(
      { k: "ssrc", timestamp: 1, rtpTimestamp: 2 },
      { k: "playout", delay: 1, samples: 2 },
      ev("botReady"),
      { k: "ev", name: "serverMessage", data: { type: "ui", cmd: "cues", ctx: "x" } },
    );
    expect(c.replay()).toEqual([]);
  });

  test("a call that ends forgets everything", () => {
    const c = fed(avatar({ cmd: "state", state: "THINKING" }), ev("botStartedSpeaking"), sync("a"), cues("a", 0));
    c.clear();
    expect(c.replay()).toEqual([]);
  });
});
